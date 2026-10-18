# PrusaSlicer-MCP v1 (motor CLI) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servidor MCP en Python que controla el PrusaSlicer 2.9 oficial por su CLI (perfiles, sesión de cama, laminado verificado, análisis de G-code, visor e impresoras en red), probado en Windows y publicado como `JorgeAlbareda/PrusaSlicer-MCP` v0.1.0.

**Architecture:** Paquete `prusaslicer_mcp` con capas puras (parseo de ini, sesión, análisis de G-code, confirmaciones) y una capa de E/S (`runner` → CLI, `hosts` → HTTP). `CliEngine` implementa el protocolo `Engine`, que en la v2 implementará también `GuiEngine`. `server.py` expone las herramientas MCP sobre el `Engine` activo.

**Tech Stack:** Python ≥ 3.11, `uv`, SDK oficial `mcp` (`mcp.server.fastmcp.FastMCP`), `anyio`, `httpx`, `pytest`, `pytest-asyncio`, GitHub Actions (`windows-latest`).

**Spec:** `docs/superpowers/specs/2026-10-18-prusaslicer-mcp-design.md` (DEFINITIVA; leer entera, en especial 4.2.1, 4.4, 4.5 y **4.9, que prevalece**). Orden de ejecución: 1, 2, 3, 4, 5, 6, 7, **9**, 8, 10, 11, 12, 13, 14, 15.

## Global Constraints

- Repositorio público `JorgeAlbareda/PrusaSlicer-MCP`, licencia **AGPL-3.0**, README con aviso "proyecto no oficial, sin afiliación con Prusa Research".
- Submódulo `deps/PrusaSlicer` → `https://github.com/prusa3d/PrusaSlicer` en el tag `version_2.9.6`, sin modificar, con `shallow = true`.
- Python `>=3.11`. Paquete `prusaslicer-mcp`, módulo `prusaslicer_mcp`, entry point de consola `prusaslicer-mcp`, transporte STDIO.
- Se acepta cualquier PrusaSlicer 2.9.x; con otra versión, aviso en `get_slicer_info` y en el log, sin fallar.
- El G-code de la v1 es siempre de texto: toda llamada de laminado lleva `--no-binary-gcode`.
- Todo `slice` verifica la configuración efectiva (spec 4.5) y falla si no coincide.
- Nunca se escribe en el datadir real del usuario durante las pruebas. Las pruebas usan datadirs temporales.
- Iniciar, pausar, reanudar o cancelar una impresión requiere confirmación humana (spec 4.3): *elicitation* o código de un solo uso con caducidad de **120 s**.
- Solo un extrusor. Si un perfil de impresora tiene `extruders_cnt > 1`, se avisa: "perfiles multiextrusor no soportados en esta versión".
- Las herramientas v2-only (`set_variable_layer_height`, `add_height_range_modifier`, `preview_layer`) existen y devuelven el error `"Requiere el motor GUI (v2)"`.
- Mensajes al usuario (errores y avisos de herramientas) en **español**; código, identificadores y README en **inglés** (proyecto público). **[decisión de Claude]**
- Pruebas que necesitan PrusaSlicer real: marcador `@pytest.mark.slicer`; se omiten si no se encuentra el ejecutable, **salvo** que `PRUSASLICER_REQUIRE=1`, en cuyo caso fallan (se activa en CI). Pruebas que lanzan procesos GUI: nunca en CI.
- **La spec 4.9 prevalece.** Control físico de impresora solo con `PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1`. `post_process` forzado a vacío salvo `PRUSASLICER_MCP_ALLOW_POST_PROCESS=1`. Todo cambio de estado pasa por el `Engine`. Siempre `--dont-arrange`, con posiciones calculadas por el servidor. El CLI y el HTTP se ejecutan con `anyio.to_thread.run_sync`. Las mutaciones van bajo un `asyncio.Lock`.

## Review Focus

1. **Rutas con espacios y caracteres no ASCII** (`C:\Users\Jorge\Desarrollo\Prusa Slicer 2.6 MCP\…`, `Piezas/Engranaje ñ.stl`): las llamadas al CLI deben funcionar. → prueba `test_slice_path_with_spaces_and_unicode` en Task 8.
2. **Nombres de perfil con `@`, espacios o comillas** (`"0.20mm SPEED @MK4S 0.4"`, `filament_settings_id = "K2M PLA"` entre comillas en el G-code): la verificación no debe dar falsos negativos. → prueba `test_verify_quoted_ids` en Task 6.
3. **Modelo que no cabe en la cama, o fuera de ella:** debe dar un error claro, no un G-code a medias. → prueba `test_slice_model_too_big_errors` en Task 8.
4. **G-code muy grande** (cientos de MB): el análisis debe leer en *streaming*, sin cargar el archivo entero en memoria, y responder en tiempo razonable. → prueba `test_toolpaths_streaming_does_not_readlines` en Task 9.
5. **PrusaSlicer bloqueado o lento:** sin un timeout, el servidor MCP se queda colgado. → prueba `test_run_cli_timeout` en Task 4.

---

## File Structure

```text
PrusaSlicer-MCP/
├── .github/workflows/ci.yml
├── .gitmodules                      # deps/PrusaSlicer @ version_2.9.6
├── deps/PrusaSlicer/                # submodule
├── docs/
│   ├── legacy/                      # borrador original + ini original de la Kobra (histórico)
│   └── superpowers/{specs,plans}/
├── examples/profiles/kobra2max/     # print/, filament/, printer/ *.ini + README.md
├── src/prusaslicer_mcp/
│   ├── __init__.py                  # __version__ = "0.1.0"
│   ├── __main__.py                  # python -m prusaslicer_mcp → server.main()
│   ├── errors.py                    # jerarquía de excepciones
│   ├── install.py                   # localizar PrusaSlicer y su versión
│   ├── ini.py                       # parseo/escritura de config plano y bundles
│   ├── runner.py                    # ejecutar el CLI, clasificar salida
│   ├── datadir.py                   # datadir, listados de perfiles, guardar perfiles de usuario
│   ├── session.py                   # estado de la cama (puro)
│   ├── verify.py                    # config efectiva del G-code y comparación
│   ├── engine.py                    # Protocol Engine + resultados comunes
│   ├── cli_engine.py                # CliEngine
│   ├── gcode/{__init__,metrics,toolpaths,risks}.py
│   ├── display.py                   # abrir en PrusaSlicer / visor de G-code
│   ├── hosts/{__init__,config,base,octoprint,moonraker,prusalink}.py
│   ├── confirm.py                   # códigos de un solo uso
│   └── server.py                    # FastMCP + herramientas
├── tests/
│   ├── conftest.py                  # fixtures: install, datadirs temporales, modelos
│   ├── models/                      # modelos de prueba + NOTICE.md (origen y licencia)
│   ├── fixtures/                    # mini G-codes, ini bundle de la Kobra
│   └── test_*.py
├── pyproject.toml
├── LICENSE
└── README.md
```

---

### Task 1: Repositorio, esqueleto y CI

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `.gitmodules`, `src/prusaslicer_mcp/__init__.py`, `src/prusaslicer_mcp/__main__.py`, `src/prusaslicer_mcp/errors.py`, `tests/test_smoke.py`, `.github/workflows/ci.yml`
- Move: `PROMPT_CLAUDE_CLI_PRUSA_MCP.md` y `Kobra2MAX_Standard_PrusaSlicer (1).ini` → `docs/legacy/` (el ini renombrado a `Kobra2MAX_Standard_PrusaSlicer.ini`)

**Interfaces:**
- Produces: `prusaslicer_mcp.__version__ == "0.1.0"`; `errors.py` con `class PrusaMcpError(Exception)` y las subclases `SlicerNotFoundError`, `CliError`, `CliTimeoutError`, `BundleIniError`, `ProfileNotFoundError`, `VerificationError`, `BinaryGcodeError`, `HostError`, `ConfirmationError`, `EngineCapabilityError`. Todas llevan `message: str` en español.

- [ ] **Step 1:** `git init` en `C:\Users\Jorge\Desarrollo\Prusa Slicer 2.6 MCP`, rama `main`. Mover los archivos legados con `git mv` tras el primer commit, o moverlos antes de añadirlos.
- [ ] **Step 2:** `git submodule add https://github.com/prusa3d/PrusaSlicer deps/PrusaSlicer`, `git -C deps/PrusaSlicer checkout version_2.9.6`, y añadir `shallow = true` en `.gitmodules`. Verificar con `git -C deps/PrusaSlicer describe --tags` → `version_2.9.6`.
- [ ] **Step 3:** `pyproject.toml` con build backend `hatchling`, `requires-python = ">=3.11"`, dependencias `mcp>=1.10`, `httpx>=0.27`, grupo dev `pytest>=8`, `pytest-asyncio>=0.23`, script `prusaslicer-mcp = "prusaslicer_mcp.server:main"`, marcador pytest `slicer`, `asyncio_mode = "auto"`. LICENSE con el texto oficial de AGPL-3.0. README breve (qué es, aviso de no afiliación, estado "v1 en desarrollo").
- [ ] **Step 4:** Test `tests/test_smoke.py::test_version`: `assert prusaslicer_mcp.__version__ == "0.1.0"`. Ejecutar `uv run pytest -q` → 1 passed.
- [ ] **Step 5:** `ci.yml`: `windows-latest`; checkout **sin** submódulos; `astral-sh/setup-uv`; descargar `https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.9.6/PrusaSlicer-2.9.6.zip` (en caché con `actions/cache`, clave `prusaslicer-2.9.6`), descomprimir y exportar `PRUSASLICER_PATH` a la carpeta que contiene `prusa-slicer-console.exe` (localizarla con `Get-ChildItem -Recurse`) y `PRUSASLICER_REQUIRE=1`; `uv run pytest -q`.
- [ ] **Step 6:** Crear el repositorio: `gh repo create JorgeAlbareda/PrusaSlicer-MCP --public --description "Unofficial MCP server for PrusaSlicer (CLI engine now, live GUI bridge next)" --source . --push`. Verificar que el CI pasa con `gh run watch`.
- [ ] **Step 7:** Commit `chore: bootstrap repository, license, CI and PrusaSlicer 2.9.6 submodule`.

### Task 2: Localizar PrusaSlicer (`install.py`)

**Files:** Create `src/prusaslicer_mcp/install.py`, `tests/conftest.py`, `tests/test_install.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class SlicerInstall: console: Path; gui: Path | None; gcodeviewer: Path | None; resources: Path | None; version: str` y `find_installation(override: str | Path | None = None) -> SlicerInstall` (lanza `SlicerNotFoundError`). Además `is_supported_version(version: str) -> bool` (True si empieza por `2.9.`), `CANDIDATE_DIRS: dict[str, list[Path]]` por `sys.platform`.
- Fixture `install` en `conftest.py`: `find_installation()`. Si no lo encuentra, hace `pytest.skip`, o `pytest.fail` si `PRUSASLICER_REQUIRE=1`. Las pruebas `slicer` la usan.

- [ ] **Step 1:** Tests: `test_override_dir_with_fake_exe` (carpeta temporal con `prusa-slicer-console.exe` falso → `console` apunta a él; la versión se inyecta con monkeypatch de `_read_version`); `test_env_var_used` (`PRUSASLICER_PATH`); `test_not_found_raises` (sin candidatos → `SlicerNotFoundError` cuyo mensaje menciona `PRUSASLICER_PATH`); `test_is_supported_version` (`"2.9.4"` → True, `"2.8.1"` → False); `@slicer test_real_install_version` (versión con regex `^\d+\.\d+\.\d+`).
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar. Orden: `override` → `PRUSASLICER_PATH` → candidatos de la plataforma. En Windows: `%ProgramFiles%\Prusa3D\PrusaSlicer`, `%ProgramW6432%\Prusa3D\PrusaSlicer`, `%LOCALAPPDATA%\Programs\PrusaSlicer`. Para darwin y linux: `/Applications/PrusaSlicer.app/Contents/MacOS`, `/usr/bin`, `/usr/local/bin` y `~/Applications` (sin probar, documentado). En Windows los ejecutables son `prusa-slicer-console.exe`, `prusa-slicer.exe` y `prusa-gcodeviewer.exe`; `resources` = `<dir>/resources` si existe. La versión sale de la primera línea de `--help` con la regex `PrusaSlicer-(\d+\.\d+\.\d+)` (salida real: `PrusaSlicer-2.9.4 based on Slic3r…`), con timeout de 30 s.
- [ ] **Step 4:** Ejecutar → PASS. Commit `feat: locate PrusaSlicer installation`.

### Task 3: Ficheros ini (`ini.py`)

**Files:** Create `src/prusaslicer_mcp/ini.py`, `tests/test_ini.py`, `tests/fixtures/kobra2max_bundle.ini` (copia del ini legado)

**Interfaces:**
- Produces: `parse_flat(text: str) -> dict[str, str]`, `is_bundle(text: str) -> bool`, `parse_bundle(text: str) -> dict[str, dict[str, dict[str, str]]]` (clave exterior `"print" | "filament" | "printer" | "presets"`, después el nombre del preset), `dump_flat(values: dict[str, str]) -> str`, `load_flat_file(path: Path) -> dict[str, str]` (lanza `BundleIniError` si `is_bundle`, con un mensaje que explica el fallo silencioso de PrusaSlicer y sugiere la herramienta `import_profile_bundle`).

- [ ] **Step 1:** Tests: `test_parse_flat_ignores_comments_and_blank`; `test_values_keep_inner_spaces_and_escaped_newlines` (`start_gcode = G90\nM83` se conserva literal con `\n`); `test_is_bundle_true_for_kobra_fixture`; `test_parse_bundle_kobra` (`["print"]["0.20mm Standard @Kobra2MAX"]["layer_height"] == "0.2"` y `["printer"]["Anycubic Kobra 2 MAX"]["bed_shape"] == "0x0,430x0,430x430,0x430"`); `test_load_flat_file_rejects_bundle`; `test_roundtrip_dump_parse`.
- [ ] **Step 2:** FAIL → **Step 3:** implementar (el separador es el primer ` = `; las claves sin valor dan `""`) → **Step 4:** PASS → commit `feat: ini parsing with bundle detection`.

### Task 4: Ejecutar el CLI (`runner.py`)

**Files:** Create `src/prusaslicer_mcp/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `SlicerInstall`.
- Produces: `@dataclass class CliResult: args: list[str]; returncode: int; stdout: str; stderr: str; warnings: list[str]; errors: list[str]` y `run_cli(install: SlicerInstall, args: list[str], *, timeout: float = 600, cwd: Path | None = None) -> CliResult`. Lanza `CliTimeoutError` si se pasa del tiempo (el proceso se mata) y `CliError` si `returncode != 0` (el mensaje incluye las `errors`). También `classify_output(text: str) -> tuple[list[str], list[str]]` (avisos, errores).

- [ ] **Step 1:** Tests de `classify_output` con texto real:
  - una línea `[error]   Error in a preset file: … contains the following incorrect keys: extrusion_axis, which were removed` → aviso;
  - el bloque `Print warning: Detected print stability issues:\n\n3DBenchy.stl\nLow bed adhesion\n\nConsider enabling supports.` → **un** aviso con el bloque unido;
  - `Print profile '0.20mm SPEED @PG' wasn't found.` → error;
  - `"G92 E0" was found in before_layer_gcode, which is incompatible with absolute extruder addressing.` → error;
  - líneas `10 => Processing triangulated mesh` → se descartan.

  Además, `test_run_cli_timeout`: con un `SlicerInstall` cuyo `console` es `sys.executable` y `args=["-c","import time; time.sleep(10)"]` y `timeout=1` → `CliTimeoutError`.
- [ ] **Step 2:** FAIL → **Step 3:** implementar con `subprocess.run` (lista de argumentos, sin `shell`, `encoding="utf-8", errors="replace"`, se combinan stdout y stderr para clasificar). La palabra `error` va en minúsculas en los logs de boost (`[error]`). Toda línea que no sea de progreso y contenga `wasn't found`, `incompatible`, `Error` o `error:`, y que no sea el caso de claves eliminadas, es error. → **Step 4:** PASS → commit `feat: CLI runner with output classification and timeout`.

### Task 5: Datadir y perfiles (`datadir.py`)

**Files:** Create `src/prusaslicer_mcp/datadir.py`, `src/prusaslicer_mcp/preset_keys.py`, `src/prusaslicer_mcp/data/preset_keys.json`, `scripts/gen_preset_keys.py`, `tests/test_datadir.py`, `examples/profiles/kobra2max/**`; añadir fixtures en `tests/conftest.py`.

**Interfaces:**
- Consumes: `run_cli`, `parse_flat`, `parse_bundle`, `dump_flat`.
- Produces:
  - `default_datadir() -> Path`: Windows `%APPDATA%\PrusaSlicer`, darwin `~/Library/Application Support/PrusaSlicer`, linux `~/.config/PrusaSlicer`.
  - `@dataclass class PrinterInfo: name: str; vendor: str; model: str; extruders: int; bed_width: float; bed_depth: float; max_height: float; user: bool`.
  - `list_printers(install, datadir: Path) -> list[PrinterInfo]` usa `--query-printer-models -o <tmp>.json`. Recorre `printer_models[*].variants[*].printer_profiles` y `user_printer_profiles`, o `printer_models[*].printer_profiles` cuando no hay variantes. Tolera `"printer_models": ""` (lista vacía) y nombres de variante numéricos.
  - `@dataclass class PrintProfileInfo: name: str; user: bool; filaments: list[str]` y `list_compatible_profiles(install, datadir, printer: str) -> list[PrintProfileInfo]` usa `--printer-profile <p> --query-print-filament-profiles`. Une `print_profiles` y `user_print_profiles`, y en cada uno `filament_profiles` y `user_filament_profiles`. Con `""` devuelve una lista vacía.
  - `save_user_preset(datadir, kind: Literal["print","filament","printer"], name: str, values: dict[str,str], *, overwrite: bool = False) -> Path` escribe `<datadir>/<kind>/<name>.ini` de forma **atómica** (`<name>.ini.tmp` + `os.replace`). Si el archivo existe y `overwrite` es False, lanza `PrusaMcpError`. Si sobrescribe, antes copia a `<datadir>/<kind>/<name>.ini.bak-<YYYYmmdd-HHMMSS>`. Rechaza nombres con `/ \ : * ? " < > |`.
  - `import_bundle(datadir, bundle_text: str, *, overwrite=False) -> tuple[list[Path], list[str]]` (rutas, avisos) escribe cada sección del bundle como preset de usuario.
    - Resuelve `inherits` dentro del propio bundle aplanando de forma recursiva: los valores del hijo pisan a los del padre, y un ciclo lanza `PrusaMcpError`.
    - Si el padre no está en el bundle, conserva `inherits` y avisa.
    - Omite `Hostname`, `post_process_enable` y `post_process` (este último salvo `PRUSASLICER_MCP_ALLOW_POST_PROCESS=1`), y avisa de lo omitido.
  - `preset_keys.py`:
    - `KEY_KIND: dict[str, Literal["print","filament","printer"]]` se carga de `src/prusaslicer_mcp/data/preset_keys.json`.
    - `classify_key(key: str) -> Literal["print","filament","printer"] | None`.
    - El JSON lo genera `scripts/gen_preset_keys.py`. El script parsea en `deps/PrusaSlicer/src/libslic3r/Preset.cpp` los literales de `s_Preset_print_options`, `s_Preset_filament_options`, `s_Preset_machine_limits_options` (→ printer) y `s_Preset_printer_options`. Se ejecuta una vez y el JSON se commitea.
  - `resolve_preset_values(install, datadir, kind, name) -> dict[str, str] | None` da los valores esperados para la verificación.
    - Perfil de usuario: se lee `<datadir>/<kind>/<name>.ini`, y si tiene `inherits`, se resuelve recursivamente contra los bundles de `<datadir>/vendor/*.ini`.
    - Perfil de sistema: se busca la sección `[<kind>:<name>]` en `<datadir>/vendor/*.ini` y se resuelve `inherits` dentro del bundle (los nombres que empiezan por `*` son plantillas abstractas del mismo archivo).
    - Si no se encuentra, devuelve `None`.
- Fixtures en `conftest.py`:
  - `vendor_datadir(tmp_path, install)`: copia `<resources>/profiles/PrusaResearch.ini` a `vendor/` y escribe `PrusaSlicer.ini` con `[vendor:PrusaResearch]\nmodel:MK4S = 0.4\n`.
  - `kobra_datadir(tmp_path)`: copia los presets de `examples/profiles/kobra2max/` y escribe un `PrusaSlicer.ini` vacío.

  Constantes de prueba: `MK4S = ("Original Prusa MK4S 0.4 nozzle", "0.20mm SPEED @MK4S 0.4", "Prusament PLA @MK4S")` y `KOBRA = ("Anycubic Kobra 2 MAX", "0.20mm Standard @Kobra2MAX", "Anycubic PLA @Kobra2MAX")`.

- [ ] **Step 1:** Crear `examples/profiles/kobra2max/{printer,print,filament}/<nombre>.ini` a partir del bundle legado con todas las correcciones de la spec 4.8 (`use_relative_e_distances = 1`, `compatible_printers_condition = printer_model=="KOBRA2MAX"`, `printer_notes` con comillas simples correctas, `default_print_profile = 0.20mm Standard @Kobra2MAX`, `default_filament_profile = Anycubic PLA @Kobra2MAX`, sin `Hostname` ni `post_process_enable`, `filament_density = 1.24`, `filament_cost = 20`, comentario de purga "Extrude 40mm"). Quitar las claves que PrusaSlicer 2.9 reporta como eliminadas: `extrusion_axis`, `duplicate_distance`, `extruder_clearance_height`, `extruder_clearance_radius`, `wipe_into_infill`, `wipe_into_objects`, `wiping_volumes_matrix`, `wiping_volumes_extruders`. Añadir un README con la instalación: copiar las tres carpetas al datadir.
- [ ] **Step 2:** Tests:
  - `test_default_datadir_windows` (monkeypatch de `APPDATA`);
  - `@slicer test_list_printers_vendor` (contiene `"Original Prusa MK4S 0.4 nozzle"`, `bed_width == 250`);
  - `@slicer test_list_printers_user_kobra` (un `PrinterInfo` con `user=True` y `bed_width == 430`);
  - `@slicer test_compatible_profiles_mk4s` (`"0.20mm SPEED @MK4S 0.4"` presente y su lista de filamentos contiene `"Prusament PLA @MK4S"`);
  - `test_save_user_preset_refuses_overwrite` y `test_save_user_preset_backup_on_overwrite`;
  - `test_import_bundle_kobra_fixture` (3 archivos y `Hostname` omitido);
  - `test_import_bundle_resolves_inherits`: bundle sintético con `[printer:Base]` (`bed_shape`, `temperature`, `start_gcode`) y `[printer:Child]` con `inherits = Base` y solo `nozzle_diameter`. El `Child.ini` escrito contiene los tres valores del padre y no tiene `inherits`;
  - `test_import_bundle_inherits_cycle_errors`;
  - `test_import_bundle_strips_post_process`;
  - `test_classify_key` (`fill_density`→print, `temperature`→filament, `bed_shape`→printer, `machine_max_feedrate_x`→printer, `foo`→None);
  - `@slicer test_resolve_system_preset_values` (`resolve_preset_values(..., "printer", "Original Prusa MK4S 0.4 nozzle")["nozzle_diameter"] == "0.4"`);
  - `@slicer test_example_kobra_profiles_load_cleanly`: laminar `20mm_cube.obj` con `KOBRA` sin avisos de claves eliminadas. Depende de Task 4; se puede usar `run_cli` directamente.
- [ ] **Step 3:** FAIL → implementar → PASS → commit `feat: datadir profile listing, user presets and Kobra 2 MAX example`.

### Task 6: Verificación (`verify.py`)

**Files:** Create `src/prusaslicer_mcp/verify.py`, `tests/test_verify.py`, `tests/fixtures/tail_kobra.gcode` (las últimas ~400 líneas de un G-code real laminado con `KOBRA`)

**Interfaces:**
- Produces:
  - `read_effective_config(gcode: Path) -> dict[str, str]`: busca desde el final del archivo (bloques de 1 MB hacia atrás) la línea `; prusaslicer_config = begin` y parsea las líneas `; clave = valor` hasta `; prusaslicer_config = end`. Si el archivo empieza por `b"GCDE"` lanza `BinaryGcodeError`.
  - `@dataclass class Mismatch: key: str; expected: str; actual: str | None`.
  - `normalize(value: str) -> str`: quita las comillas dobles exteriores; un número se normaliza con `float` y se formatea con `repr`, sin ceros inútiles; mantiene el `%`.
  - `compare(effective: dict[str,str], expected: dict[str,str]) -> list[Mismatch]`.
  - `CRITICAL_KEYS: tuple[str, ...]` = las 12 claves de la spec 4.9.2.
  - `@dataclass class Verification: ok: bool; checked_keys: list[str]; unchecked_keys: list[str]; mismatches: list[Mismatch]`.
  - `build_expected(ids: dict[str,str], source_values: dict[str,str] | None, overrides: dict[str,str]) -> tuple[dict[str,str], list[str]]` (esperado, sin comprobar). Une los ids de perfil, las `CRITICAL_KEYS` presentes en `source_values` (fusión de los valores resueltos de los tres perfiles, o del `config_file`) y los overrides, que tienen prioridad. Las claves críticas que no están en `source_values` van a la lista de sin comprobar.
  - `verify(gcode: Path, expected: dict[str,str], unchecked: list[str]) -> Verification`.
  - `expected_ids(printer: str, print_: str, filaments: list[str]) -> dict[str,str]` devuelve `printer_settings_id`, `print_settings_id` y `filament_settings_id` (los filamentos unidos con `;`).

- [ ] **Step 1:** Tests:
  - `test_read_effective_config_fixture` (`bed_shape == "0x0,430x0,430x430,0x430"`);
  - `test_binary_gcode_rejected` (archivo que empieza por `GCDE\x01\x00`);
  - `test_verify_quoted_ids` (`filament_settings_id = "K2M PLA"` frente al esperado `K2M PLA` → sin diferencias);
  - `test_numeric_normalization` (`0.20` frente a `0.2`, `15%` frente a `15%`);
  - `test_mismatch_reported` (`fill_density` esperado `40%`, real `15%` → un `Mismatch`);
  - `test_missing_key_reported` (`actual is None`);
  - `test_build_expected_overrides_win_and_unchecked_listed` (override `layer_height=0.15` sobre un origen con `0.2` → se espera `0.15`; si el origen no tiene `nozzle_diameter`, esa clave aparece en `unchecked`).
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: effective-config verification`.

### Task 7: Sesión, colocación y protocolo de motor (`session.py`, `placement.py`, `engine.py`)

**Files:** Create `src/prusaslicer_mcp/session.py`, `src/prusaslicer_mcp/placement.py`, `src/prusaslicer_mcp/engine.py`, `tests/test_session.py`, `tests/test_placement.py`

**Interfaces:**
- Produces (`session.py`, puro):
  - `@dataclass class Instance: center: tuple[float, float] | None = None; fixed: bool = False` (`fixed=True` cuando lo posiciona el usuario).
  - `@dataclass class PlateObject: id: int; path: Path; rotate_z: float = 0; rotate_x: float = 0; rotate_y: float = 0; scale_percent: float = 100; instances: list[Instance] = [Instance()]; extruder: int = 1`.
  - `@dataclass class Session: printer: str | None = None; print_profile: str | None = None; filaments: list[str] = []; config_file: Path | None = None; overrides: dict[str,str] = {}; objects: list[PlateObject] = []`.
  - Métodos de `Session`:
    - `add_object(path: Path, copies: int = 1) -> PlateObject`: ids incrementales desde 1 que no se reutilizan. Comprueba que el archivo existe y que la extensión está en `{".stl",".3mf",".obj",".step",".stp",".amf"}`.
    - `remove_object(id) -> None`, `clear() -> None`.
    - `transform(id, *, rotate_z=None, rotate_x=None, rotate_y=None, scale_percent=None, copies=None) -> PlateObject`: valores absolutos. Si cambian rotación o escala, se pierden las posiciones no fijas. `copies` ajusta la lista de instancias: añade instancias sin posición o quita las últimas.
    - `place(id, instance: int, x: float, y: float) -> None` pone `fixed=True`.
    - `unplace_all(include_fixed: bool = False) -> None` borra las posiciones no fijas y, con `include_fixed=True`, también las fijas.
    - `set_setting(key, value)`, `reset_setting(key)`, `select_profiles(printer, print_profile, filaments)`, `snapshot() -> Session` (`copy.deepcopy`) y `to_dict() -> dict`.
- Produces (`placement.py`, puro):
  - `@dataclass class Footprint: object_id: int; instance: int; width: float; depth: float; center: tuple[float,float] | None; fixed: bool`.
  - `parse_bed_shape("0x0,430x0,430x430,0x430") -> tuple[float,float,float,float]` (min_x, min_y, max_x, max_y).
  - `pack(footprints: list[Footprint], bed: tuple[float,float,float,float], spacing: float = 6.0) -> list[Footprint]` mantiene las fijas y coloca el resto. Algoritmo: estantes (*shelf*) de izquierda a derecha y de abajo arriba, ordenando por profundidad descendente; se salta cualquier hueco que solape con una fija (más `spacing`). Si alguna no cabe, lanza `PrusaMcpError("No caben todas las piezas en la cama: …")`.
  - `validate(footprints, bed, spacing) -> list[str]` devuelve problemas: fuera de la cama o solapes, con el margen `spacing / 2` por lado. El texto de un solape contiene "solapa".
- Produces (`engine.py`):
  - `@dataclass class SliceResult: gcode_path: Path; metrics: "GcodeMetrics"; warnings: list[str]; verification: Verification; placements: list[Footprint]`.
  - `class Engine(Protocol)`: todo cambio de estado pasa por aquí (spec 4.9.4).
    - Atributo `name: str`.
    - Lectura: `info() -> dict`, `list_printers() -> list[PrinterInfo]`, `list_compatible_profiles(printer) -> list[PrintProfileInfo]`, `get_plate() -> dict`, `get_setting(key) -> str | None`.
    - Cambios de estado: `select_profiles(printer, print_profile, filaments) -> list[str]` (avisos), `use_config_file(path) -> None`, `set_setting(key, value) -> None`, `reset_setting(key) -> None`, `add_model(path, copies=1) -> dict` (objeto + `model_info`), `remove_object(id) -> None`, `clear_plate() -> None`, `transform_object(id, **kw) -> dict`, `place_instance(id, instance, x, y) -> None`, `arrange_plate() -> list[Footprint]`.
    - Acciones: `slice(output: Path | None) -> SliceResult`, `export_3mf(output: Path) -> Path`, `save_profile_as(kind, name, keys=None, overwrite=False) -> Path`.
    - Solo v2: `set_variable_layer_height(object_id, quality)`, `add_height_range_modifier(object_id, z_from, z_to, settings)` y `preview_layer(layer)`.

- [ ] **Step 1:** Tests de `Session`: ids que no se reutilizan; extensión no soportada → error; `transform` absoluto; `copies=3` → 3 instancias; un cambio de rotación borra las posiciones no fijas y conserva las fijas; `snapshot` independiente. Tests de `placement`: `test_pack_two_cubes_no_overlap`; `test_pack_respects_fixed`; `test_pack_too_many_errors` (30 piezas de 100×100 en una cama de 250×210 → error); `test_validate_detects_overlap_and_out_of_bed`; `test_parse_bed_shape`.
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: session, deterministic placement and engine protocol`.

### Task 8: `CliEngine`

**Files:** Create `src/prusaslicer_mcp/cli_engine.py`, `tests/test_cli_engine.py`, `tests/models/` + `tests/models/NOTICE.md`

**Interfaces:**
- Consumes: Tasks 2–7 y `get_gcode_metrics` / `analyze_toolpaths` de Task 9 (se implementa **antes** de esta tarea).
- Produces: `class CliEngine(Engine)` con `__init__(self, install: SlicerInstall, datadir: Path, workdir: Path, allow_post_process: bool = False)` y `name = "cli"`. Guarda la `Session`, que es privada. Los métodos v2-only lanzan `EngineCapabilityError("Requiere el motor GUI (v2)")`. `set_setting("post_process", …)` sin permiso lanza `PrusaMcpError`.

Algoritmo de `slice` (documentado aquí porque ni la firma ni los tests lo determinan):
1. `s = session.snapshot()` y `job = <workdir>/<pid>/<uuid4>/`.
2. Validar `s`: hay objetos; o bien `config_file` (pasado por `load_flat_file`, que rechaza bundles), o bien los tres perfiles.
3. Huellas: para cada objeto se exporta un 3MF con su transformación (`--rotate`, `--rotate-x`, `--rotate-y`, `--scale S%`, `--export-3mf`), en caché en `<workdir>/<pid>/cache/` por hash de (ruta, mtime, transformación). Con `--info` sobre ese 3MF se obtienen `size_x` y `size_y`, que forman una `Footprint` por instancia.
4. `pack` (con `spacing` = `duplicate_distance` del perfil si existe, o 6) seguido de `validate`. Si `validate` devuelve problemas → `PrusaMcpError` con la lista.
5. Por cada instancia: `--center x,y --export-3mf -o job/inst-<id>-<n>.3mf <3mf transformado>`.
6. Overrides: `dict(s.overrides)`. Si `allow_post_process` es False se añade `post_process = ""`. Se escribe con `dump_flat` en `job/overrides.ini`.
7. Comando final: `[--datadir D, --printer-profile, --print-profile, --material-profile (filamentos unidos con ";") | --load config_file, --load job/overrides.ini, --no-binary-gcode, --merge, --dont-arrange, --export-gcode, -o job/out.gcode, <inst-*.3mf…>]`. Con una sola instancia se omiten `--merge` y `--dont-arrange`. Se ejecuta con `run_cli`.
8. Verificación:
   - `source_values` = fusión de `resolve_preset_values` de printer, print y filament (o `load_flat_file(config_file)`);
   - `expected, unchecked = build_expected(expected_ids(...) | {}, source_values, overrides_de_sesión)`;
   - `v = verify(job/out.gcode, expected, unchecked)`.

   Si `not v.ok` → `VerificationError` con `v`. El G-code se queda en `job/` para poder revisarlo y **no** se publica.
9. Si `v.ok`, se mueve con `os.replace` a la salida pedida o a la de por defecto, `<workdir>/output/<stem>-<YYYYmmdd-HHMMSS>-<uuid8>.gcode`.
10. Si el `PrinterInfo` tiene `extruders > 1` → aviso de multiextrusor.
11. Se devuelve `SliceResult(..., placements=footprints)`.

`arrange_plate()` = `unplace_all()` + los pasos 3 y 4. Escribe las posiciones resueltas en la sesión (como no fijas) y las devuelve. `model_info(path)` = `--info <path>`, del que se parsean las líneas `clave = valor` (`size_x`, `size_y`, `size_z`, `number_of_facets`, `manifold`, `volume`).

- [ ] **Step 1:** Copiar a `tests/models/` desde `deps/PrusaSlicer/tests/data`: `20mm_cube.obj`, `bridge.obj`, `overhang.obj`, `U_overhang.obj`, `cube_with_hole.obj`, `pyramid.obj`. Desde `deps/PrusaSlicer/resources/shapes`: `3DBenchy.stl` y `cylinder.stl`. `NOTICE.md` indica el origen de cada archivo (repositorio PrusaSlicer, tag `version_2.9.6`, AGPL-3.0).
- [ ] **Step 2:** Tests `@slicer`:
  - `test_slice_mk4s_cube_verified`: `verification.ok`, `"nozzle_diameter" in checked_keys`, `printer_model == "MK4S"` y el archivo no empieza por `GCDE`.
  - `test_slice_kobra_benchy`: `bed_shape` de 430.
  - `test_override_changes_result`: con `fill_density=40%` se gasta más filamento que con `15%`.
  - `test_two_objects_positions_resolved`: cubo + cilindro con copies=2 en la Kobra → 3 `placements` y `validate(...) == []`. Además, el bbox XY de las extrusiones de la primera capa (`analyze_toolpaths(...).layers[0].bbox`) contiene todos los centros resueltos.
  - `test_fixed_position_kept`: `place_instance(1, 0, 300, 300)` → la placement de esa instancia es (300, 300).
  - `test_overlap_rejected`: dos instancias fijas en el mismo punto → `PrusaMcpError` cuyo mensaje contiene "solapa".
  - `test_post_process_not_executed`: un perfil de usuario con `post_process = "<sys.executable>" "<script que crea marker.txt>"` → tras laminar, `marker.txt` no existe y la config efectiva tiene `post_process` vacío.
  - `test_bundle_config_file_rejected`: `BundleIniError`.
  - `test_missing_profile_errors`: `CliError` con `wasn't found`.
  - `test_slice_model_too_big_errors`: Benchy con `scale_percent=1000` en la MK4S → `PrusaMcpError` con mensaje.
  - `test_slice_path_with_spaces_and_unicode`: `tmp_path/"Carpeta con espacios"/"pieza ñ.obj"`.
  - `test_failed_verification_does_not_publish`: se fuerza un esperado imposible con monkeypatch de `build_expected` → `VerificationError` y la ruta de salida pedida no existe.
  - `test_v2_only_methods_raise`.
  - `test_model_info_cube`: `size_x ≈ 20`.
- [ ] **Step 3:** FAIL → implementar → PASS → commit `feat: CLI engine with server-side placement and verified slicing`.

### Task 9: Métricas y análisis de recorridos (`gcode/metrics.py`, `gcode/toolpaths.py`)

> Esta tarea se implementa **antes** que la Task 8, porque el `CliEngine` la usa.

**Files:** Create `src/prusaslicer_mcp/gcode/__init__.py`, `metrics.py`, `toolpaths.py`, `tests/test_gcode_metrics.py`, `tests/test_toolpaths.py`, `tests/fixtures/mini.gcode`, `tests/fixtures/abs_e.gcode`

**Interfaces:**
- Produces (`metrics.py`):
  - `@dataclass class GcodeMetrics: print_time_s: int | None; print_time_silent_s: int | None; filament_mm: float | None; filament_cm3: float | None; filament_g: float | None; cost: float | None; layer_count: int; layer_height: float | None; first_layer_height: float | None; printer: str | None; print_profile: str | None; filaments: list[str]; config: dict[str,str]`.
  - `parse_duration("1d 2h 3m 4s") -> int` (→ 93784).
  - `get_gcode_metrics(path: Path) -> GcodeMetrics`: `layer_count` = número de `;LAYER_CHANGE`. Si la densidad del filamento es 0, `filament_g` es `None` (no 0). Usa `read_effective_config`.
  - `resolve_value(config: dict[str,str], key: str, base_key: str | None = None) -> float | None`: resuelve los `%` contra `base_key` (por ejemplo `first_layer_speed` en % de `perimeter_speed`) y devuelve `None` si no se puede.
- Produces (`toolpaths.py`):
  - `@dataclass class TypeStats: length_mm: float = 0; extruded_mm: float = 0; time_s: float = 0; moves: int = 0`.
  - `@dataclass class LayerStats: index: int; z: float; height: float; time_s: float; time_source: Literal["m73","estimate"]; extruded_mm: float; retractions: int; by_type: dict[str, TypeStats]; bbox: tuple[float,float,float,float] | None; contact_area_mm2: float; max_volumetric_mm3s: float; max_bridge_move_mm: float; max_vx_mm_s: float; max_vy_mm_s: float; max_accel: float`.
  - `@dataclass class ToolpathReport: by_type: dict[str, TypeStats]; layers: list[LayerStats]; travel: TypeStats; retractions: int; time_scale: float; has_type_markers: bool; unsupported: dict[str, int]; confidence: Literal["high","medium","low"]`.
  - `analyze_toolpaths(path: Path, filament_diameter: float | None = None) -> ToolpathReport`.

Máquina de estados del analizador (spec 4.9.7):
- Lectura en streaming, línea a línea con `for line in f`.
- Estado modal: `G90`/`G91` para XYZ, `M82`/`M83` para E, `G92` (cualquier eje), `F` persistente.
- ΔE de cada `G0`/`G1`/`G2`/`G3`: diferencia con la E anterior en modo absoluto, o el valor directo en relativo. Clasificación:
  - ΔE > 0 y XY > 0 → **deposición** en el `;TYPE:` actual;
  - ΔE > 0 sin XY → **des-retracción**: no cuenta como recorrido ni para el caudal;
  - ΔE < 0 → **retracción**, que suma 1 a `retractions`; si además hay XY, la distancia cuenta como viaje (limpieza);
  - ΔE = 0 con XY → **viaje**.
- Para `G2`/`G3`, la longitud del arco sale de I/J; sin I/J se cuentan en `unsupported["G2/G3 sin IJ"]`. `G10`/`G11` se cuentan como retracción por firmware en `unsupported["G10/G11"]`, igual que `G20`.
- `confidence`: `high` si `unsupported` está vacío y hay marcas de tipo; `medium` si hay ≤ 1 % de líneas no soportadas o faltan las marcas; `low` en otro caso.
- Tiempo bruto = distancia / (F/60). `time_scale` = `print_time_s` / tiempo bruto total (1 si no se conoce `print_time_s`).
- Tiempo por capa: si el archivo tiene `M73 … R<min>`, `time_s` de la capa es la diferencia de R entre su inicio y su fin, y `time_source="m73"`. Si no, es el bruto × `time_scale`, con `time_source="estimate"`.
- Velocidades por eje: `vx = |dx|/t` y `vy = |dy|/t`; se guarda el máximo por capa.
- `M204 S`/`P`: se guarda el **máximo** de la capa.
- Caudal = ΔE × área del filamento / t, solo en deposición. El diámetro se toma del argumento o de `filament_diameter` de la config efectiva.
- Capa 0: `bbox` de las deposiciones y `contact_area_mm2` = Σ(longitud × `;WIDTH:` actual).
- `max_bridge_move_mm` = el movimiento de deposición más largo en `Bridge infill`.

- [ ] **Step 1:** Fixtures escritos a mano:
  - `mini.gcode` (E relativo): 2 capas; `;TYPE:External perimeter`; `;WIDTH:0.45`; un cuadrado de 10 mm a F1200; un viaje de 5 mm; una retracción `G1 E-0.8` y su des-retracción `G1 E0.8`.
  - `abs_e.gcode` (M82): `G1 X10 E100` tras `G92 E99`, luego `G1 E99` (retracción en absoluto con E positiva), `G1 E100` (des-retracción) y `G1 X20 E100` (viaje).

  Tests:
  - `test_parse_duration` (`"41m 6s"`→2466, `"14m 31s"`→871);
  - `test_metrics_kobra_tail`;
  - `test_grams_none_when_density_zero`;
  - `test_resolve_value_percent` (`first_layer_speed=50%` con `perimeter_speed=60` → 30);
  - `test_toolpaths_mini`: `External perimeter` mide 40 mm en la capa 0; `travel` 5; `retractions == 1`; `bbox == (0,0,10,10)`; `contact_area_mm2 ≈ 40×0.45`; la des-retracción no suma recorrido;
  - `test_toolpaths_absolute_e`: 1 retracción, 0 mm de deposición tras ella y 10 mm de viaje;
  - `test_unsupported_lowers_confidence` (un `G10` → `confidence != "high"`);
  - `test_m73_layer_times` (fixture con `M73 P10 R5` / `M73 P20 R4` → `time_s == 60` y `time_source == "m73"`);
  - `test_toolpaths_streaming_does_not_readlines` (monkeypatch de `io.TextIOWrapper.readlines` y `.read` para que fallen);
  - `@slicer test_toolpaths_benchy_types` (aparecen `"Overhang perimeter"` y `"Bridge infill"`, `has_type_markers` es True y `confidence == "high"`).
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: gcode metrics and toolpath analytics`.

### Task 10: Riesgos de impresión (`gcode/risks.py`)

**Files:** Create `src/prusaslicer_mcp/gcode/risks.py`, `tests/test_risks.py`

**Interfaces:**
- Consumes: `ToolpathReport`, `GcodeMetrics.config`, `resolve_value`.
- Produces:
  - `@dataclass class Risk: kind: str; severity: Literal["info","warning","high"]; basis: Literal["measured","heuristic"]; layers: tuple[int,int] | None; message: str; evidence: dict[str, float | str]` (mensaje en español; `evidence` lleva los valores medidos y el umbral).
  - `@dataclass class RiskThresholds` con valores por defecto:
    - `short_layer_s: float | None = None` (si es None, `slowdown_below_layer_time` de la config, o 5);
    - `warp_materials = ("ABS","ASA","PC","PA","NYLON","PP")`;
    - `warp_contact_cm2 = 100.0`;
    - `bed_edge_margin_mm = 5.0`;
    - `overhang_fraction = 0.25`;
    - `bridge_move_mm = 25.0`;
    - `max_volumetric_mm3s: float | None = None` (si es None, el **mínimo** de los positivos entre `filament_max_volumetric_speed` y `max_volumetric_speed`; si ninguno es positivo, se omite);
    - `retractions_per_layer = 60`;
    - `first_layer_speed_mm_s = 60.0`.
  - `find_print_risks(report, config, thresholds=RiskThresholds()) -> list[Risk]`, ordenada por severidad y después por primera capa. Las capas consecutivas de la misma clase se agrupan en `layers=(a,b)`.

Clases (`kind` / `basis` / `severity`):
- `short_layer_time` / heuristic / `warning` si `time_source=="m73"`, `info` si es estimación (con la nota "estimación aproximada").
- `warping_risk` / heuristic:
  - `high` si `filament_type` está en `warp_materials`, `brim_width == 0` y `contact_area_mm2 / 100 ≥ warp_contact_cm2`;
  - `warning`, para cualquier material, si el bbox de la capa 0 está a menos de `bed_edge_margin_mm` del borde.
- `overhangs` / heuristic / `warning`: longitud de `Overhang perimeter` / (`Perimeter` + `External perimeter` + `Overhang perimeter`) > `overhang_fraction`.
- `long_bridge` / measured / `warning`.
- `volumetric_flow` / measured / `high`.
- `machine_limits` / measured / `warning`: `max_vx` > `machine_max_feedrate_x`, `max_vy` > `machine_max_feedrate_y` o `max_accel` > `machine_max_acceleration_extruding`. Solo si `machine_limits_usage` no es `ignore`.
- `retractions` / heuristic / `info`.
- `first_layer_speed` / measured / `warning`: `resolve_value(config,"first_layer_speed","perimeter_speed")` > umbral.

- [ ] **Step 1:** Tests con `ToolpathReport` construidos a mano:
  - uno por clase, comprobando `kind`, `basis` y que `evidence` lleva el umbral;
  - `test_volumetric_uses_stricter_limit` (límites 15 y 12, caudal 13 → riesgo);
  - `test_scattered_small_objects_no_warping` (bbox grande pero `contact_area` pequeña → sin `warping_risk` de severidad `high`);
  - `test_estimate_short_layer_is_info`;
  - `test_grouping_consecutive_layers`;
  - `test_no_risks_clean_report`;
  - `@slicer test_bridge_model_flags_bridge` (`bridge.obj` en la Kobra → hay un `long_bridge` o un `overhangs`).
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: print risk detection with evidence`.

### Task 11: Visor (`display.py`)

**Files:** Create `src/prusaslicer_mcp/display.py`, `tests/test_display.py`

**Interfaces:**
- Produces: `viewer_command(install: SlicerInstall, path: Path) -> list[str]`. Para `.gcode` usa `gcodeviewer` (o `[gui, "--gcodeviewer", path]` si no hay `gcodeviewer`); para `.3mf`, `.stl`, `.obj` y `.step` usa `[gui, "--single-instance", path]`. Si no hay GUI, lanza `SlicerNotFoundError`. También `show(install, path) -> None`, que hace `subprocess.Popen` desacoplado (`creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` en Windows) sin esperar.
- [ ] **Step 1:** Tests de `viewer_command` para las extensiones anteriores, para un `.gcode` sin `gcodeviewer` y para una extensión no soportada (→ `PrusaMcpError`). `show` no se prueba en CI.
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: open results in PrusaSlicer or the G-code viewer`.

### Task 12: Impresoras en red (`hosts/`)

**Files:** Create `src/prusaslicer_mcp/hosts/__init__.py`, `config.py`, `base.py`, `octoprint.py`, `moonraker.py`, `prusalink.py`, `tests/test_hosts.py`

**Interfaces:**
- Produces:
  - `@dataclass class HostConfig: name: str; host_type: str; url: str; api_key: str | None; user: str | None; password: str | None; auth: Literal["key","user"]; cafile: str | None; storage: str | None = None`.
  - En Moonraker, `upload` devuelve `result.item.path` de la respuesta. En OctoPrint devuelve `files.local.name`.
  - `load_physical_printers(datadir: Path) -> list[HostConfig]` lee `<datadir>/physical_printer/*.ini` (claves `host_type`, `print_host`, `printhost_apikey`, `printhost_user`, `printhost_password`, `printhost_authorization_type`, `printhost_cafile`). Si `print_host` no lleva esquema, se antepone `http://`.
  - `@dataclass class PrinterStatus: state: str; progress: float | None; file: str | None; nozzle_temp: float | None; bed_temp: float | None; raw: dict`.
  - `class PrintHost(Protocol)`: `upload(path: Path, start: bool = False) -> str` (devuelve la ruta o identificador remoto real que da el host), `status() -> PrinterStatus`, `start(remote: str) -> None`, `pause()`, `resume()` y `cancel()`. `PrinterStatus` añade el campo `job_id: str | None`, que es el id del trabajo o, si el host no lo da, el nombre del archivo en curso.
  - `make_host(cfg: HostConfig, transport: httpx.BaseTransport | None = None) -> PrintHost`. Soporta `octoprint`, `moonraker` y `prusalink`; con otro `host_type` lanza `HostError("Tipo de host no soportado: …")`.
- Endpoints (los fija la spec por cliente):
  - **OctoPrint:** cabecera `X-Api-Key`. `POST /api/files/local` (multipart `file`, `print=true|false`), `POST /api/files/local/{name}` `{"command":"select","print":true}`, `GET /api/job` + `GET /api/printer`, `POST /api/job` con `{"command":"pause","action":"pause"|"resume"}` o `{"command":"cancel"}`.
  - **Moonraker:** cabecera `X-Api-Key` si hay. `POST /server/files/upload` (multipart `file`, `print=true|false`), `POST /printer/print/start?filename=`, `GET /printer/objects/query?print_stats&virtual_sdcard&extruder&heater_bed`, `POST /printer/print/pause|resume|cancel`.
  - **PrusaLink:** `X-Api-Key` o `httpx.DigestAuth(user, password)`. almacenamiento = `HostConfig.storage` si está configurado, o el primer elemento con `available` y sin `read_only` de `GET /api/v1/storage` (campo `path`, por ejemplo `/usb`). `PUT /api/v1/files{storage}/{name}` con el cuerpo binario y las cabeceras `Print-After-Upload: ?1|?0`, `Overwrite: ?0`, `Content-Type: application/octet-stream`; un 409 → `HostError("Ya existe un archivo con ese nombre en la impresora")`. `upload` devuelve `"{storage}/{name}"`. `POST /api/v1/files{remote}` para iniciar; `GET /api/v1/status` y `GET /api/v1/job` (→ `id`); `PUT /api/v1/job/{id}/pause`, `PUT /api/v1/job/{id}/resume` y `DELETE /api/v1/job/{id}`.
- Timeouts httpx: 10 s en general y 300 s en la subida.

- [ ] **Step 1:** Tests con `httpx.MockTransport` que registra las peticiones. En PrusaLink se comprueba además: la cabecera `Overwrite: ?0`, el descubrimiento de almacenamiento y el 409 → error. `upload` devuelve la ruta remota en los tres clientes. Por cliente: la subida con `start=False` no inicia; con `start=True`, el campo o cabecera de inicio es correcto; `status` se mapea a `PrinterStatus`; pausa y cancelación usan el método y la ruta exactos de arriba; un 401 → `HostError` con mensaje "credenciales". Además `test_load_physical_printers` con un ini de ejemplo y `test_unsupported_host_type`.
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: OctoPrint, Moonraker and PrusaLink clients`.

### Task 13: Confirmaciones (`confirm.py`)

**Files:** Create `src/prusaslicer_mcp/confirm.py`, `tests/test_confirm.py`

**Interfaces:**
- Produces: `class ConfirmationGate` con:
  - `__init__(self, ttl_s: float = 120, clock: Callable[[], float] = time.monotonic)`;
  - `request(self, action: str, params: dict) -> str`, que devuelve un código de 8 caracteres de `secrets.token_urlsafe`, ligado a `action` y al JSON canónico de `params`;
  - `consume(self, code: str, action: str, params: dict) -> None`, que lanza `ConfirmationError` si el código no existe, está caducado, ya se usó o los parámetros o la acción no coinciden.
- Quien llama mete en `params` el host **y** el `job_id` actual (para pausar, reanudar o cancelar), o el archivo remoto (para iniciar). Así una aprobación no vale para otro trabajo.
- [ ] **Step 1:** Tests: camino feliz; segundo uso → error; caducidad con un reloj falso (121 s); parámetros cambiados → error; acción distinta → error; `job_id` distinto → error.
- [ ] **Step 2:** FAIL → implementar → PASS → commit `feat: one-time confirmation codes`.

### Task 14: Servidor MCP (`server.py`)

**Files:** Create `src/prusaslicer_mcp/server.py`, `tests/test_server.py`, `tests/test_e2e_stdio.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `build_server(engine: Engine | None = None, datadir: Path | None = None, gate: ConfirmationGate | None = None, host_transport: httpx.BaseTransport | None = None) -> FastMCP` y `main() -> None` (`build_server().run()` por STDIO).
- Variables de entorno:
  - `PRUSASLICER_MCP_ENGINE`: `auto` | `cli`, por defecto `auto` (en la v1, `auto` = `cli`);
  - `PRUSASLICER_PATH`;
  - `PRUSASLICER_DATADIR`, por defecto `default_datadir()`;
  - `PRUSASLICER_MCP_WORKDIR`, por defecto `<tempdir>/prusaslicer-mcp`;
  - `PRUSASLICER_MCP_ALLOW_PRINT_CONTROL` (`1` habilita start, pause, resume y cancel);
  - `PRUSASLICER_MCP_ALLOW_POST_PROCESS`.
- Toda herramienta delega en el `Engine` (spec 4.9.4). Las herramientas que cambian estado y `slice` se ejecutan bajo un `asyncio.Lock` único. Las llamadas bloqueantes (engine y hosts) van en `anyio.to_thread.run_sync`.
- Los retornos son serializables a JSON (`dataclasses.asdict`, con `Path` → `str`). Un `PrusaMcpError` se devuelve como error de herramienta con su `message`.
- Herramientas:
  - **Info y perfiles:** `get_slicer_info()` (versión, rutas, datadir, `engine`, `supported_version` y si el control de impresión está activado), `list_printers()`, `list_compatible_profiles(printer: str)`, `select_profiles(printer: str, print_profile: str, filaments: list[str])` y `use_config_file(path: str)`.
  - **Ajustes:** `get_setting(key: str)`: el override de la sesión, o el valor efectivo del último laminado, o `null` con la nota "lamina primero para ver el valor efectivo". `set_setting(key: str, value: str)`, `reset_setting(key: str)`.
  - **Perfiles de usuario:** `save_profile_as(name: str, keys: list[str] | None = None, overwrite: bool = False)` **[decisión de Claude]**. Reparte los overrides de la sesión (todos o solo `keys`) por tipo con `classify_key`, y escribe un preset de usuario por cada tipo afectado, con nombre `name` y `inherits = <preset seleccionado de ese tipo>`. Las claves sin tipo se rechazan. Después lamina un cubo de prueba con los nuevos presets como comprobación de ida y vuelta. Devuelve las rutas escritas. `import_profile_bundle(path: str, overwrite: bool = False)` devuelve rutas y avisos.
  - **Cama:** `add_model(path: str, copies: int = 1)`, `get_plate()`, `remove_object(object_id: int)`, `clear_plate()`, `transform_object(object_id: int, rotate_z: float | None = None, rotate_x: float | None = None, rotate_y: float | None = None, scale_percent: float | None = None, copies: int | None = None)`, `place_instance(object_id: int, instance: int, x: float, y: float)` y `arrange_plate()`, que devuelve las posiciones.
  - **Laminado:** `slice(output_path: str | None = None)` → `{gcode_path, metrics, warnings, verification, placements}`. `export_3mf(output_path: str)`.
  - **Análisis:** `get_gcode_metrics(gcode_path: str)`; `analyze_toolpaths(gcode_path: str, include_layers: bool = False, max_layers: int = 50)`, que por defecto devuelve `by_type`, `confidence`, `unsupported` y un resumen, y con `include_layers` como mucho `max_layers` capas (las más lentas); `find_print_risks(gcode_path: str)`.
  - **Visor:** `show_in_slicer(path: str)`.
  - **Solo v2:** `set_variable_layer_height(object_id: int, quality: float = 0.5)`, `add_height_range_modifier(object_id: int, z_from: float, z_to: float, settings: dict[str,str])` y `preview_layer(layer: int)` → error v2.
  - **Impresoras:** `list_print_hosts()` nunca devuelve `api_key` ni `password`. `upload_gcode(host: str, gcode_path: str)` devuelve `remote`. `get_printer_status(host: str)`.
  - **Control de impresión:** `start_print(host: str, remote: str, confirmation_code: str | None = None)`, `pause_print(host: str, confirmation_code: str | None = None)`, `resume_print(...)` y `cancel_print(...)`, con `ToolAnnotations(destructiveHint=True)`. Si `PRUSASLICER_MCP_ALLOW_PRINT_CONTROL` no es `1`, devuelven el error "El control de impresión está desactivado. El usuario puede activarlo con PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1 en la configuración del servidor."

**Flujo de confirmación** (en las cuatro herramientas de control, con el control activado):
1. Se calcula `params = {host, remote}` para iniciar, o `{host, job_id: status().job_id}` para el resto. Si no hay trabajo en curso al pausar o cancelar → error.
2. Si el cliente declara `elicitation` (`ctx.session.client_params.capabilities.elicitation is not None`), se hace `await ctx.elicit(message="¿<acción> <remote|job> en <host>?", schema=<modelo pydantic con confirm: bool>)`. Solo se ejecuta si `action == "accept"` y `confirm` es True.
3. Si no, sin código se devuelve `{"status":"confirmation_required","code":gate.request(...), "expires_in_s":120,"summary":..., "instructions":"Pregunta al usuario y, solo si acepta explícitamente, vuelve a llamar con confirmation_code. Esta confirmación depende del cliente."}`.
4. Con código: se vuelven a calcular `params` (el trabajo actual), se ejecuta `gate.consume` y después la acción.

- [ ] **Step 1:** Tests unitarios con un `Engine` falso (implementa el protocolo y graba llamadas) y hosts con `MockTransport`, mediante `await server.call_tool(name, args)`:
  - `test_tools_registered` (el conjunto exacto de nombres);
  - `test_state_tools_route_through_engine` (cada herramienta de cambio llega a su método del engine);
  - `test_slice_returns_verification`;
  - `test_v2_tool_error_message`;
  - `test_list_print_hosts_hides_secrets`;
  - `test_print_control_disabled_by_default`;
  - `test_start_print_two_step` (con el control activado: la primera llamada no toca el host y la segunda, con el código, sí);
  - `test_start_print_bad_code`;
  - `test_cancel_code_bound_to_job` (el trabajo cambia entre llamadas → error);
  - `test_start_print_elicitation_accept` y `test_start_print_elicitation_decline`;
  - `test_save_profile_as_splits_by_kind` (`fill_density` y `temperature` → dos presets: print y filament).
- [ ] **Step 2:** `@slicer test_e2e_stdio`: `mcp.client.stdio.stdio_client(StdioServerParameters(command=sys.executable, args=["-m","prusaslicer_mcp"], env={**os.environ, "PRUSASLICER_DATADIR": vendor_datadir}))`, después `ClientSession` e `initialize`. Llamar a `select_profiles(MK4S)`, `add_model(20mm_cube.obj, copies=2)`, `arrange_plate`, `slice`, `find_print_risks(gcode_path)` y comprobar que `verification.ok` es True y que hay 2 `placements`.
- [ ] **Step 3:** FAIL → implementar → PASS → commit `feat: MCP server exposing CLI engine tools`.

### Task 15: Documentación y publicación de v0.1.0

**Files:** Modify `README.md`; Create `docs/usage.md` (en español)

- [ ] **Step 1:** README (inglés):
  - qué es y aviso de no afiliación;
  - requisitos (PrusaSlicer 2.9.x, `uv`);
  - instalación `uvx --from git+https://github.com/JorgeAlbareda/PrusaSlicer-MCP prusaslicer-mcp`;
  - configuración en Claude Desktop (`claude_desktop_config.json`) y Claude Code (`claude mcp add prusaslicer -- uvx --from git+https://github.com/JorgeAlbareda/PrusaSlicer-MCP prusaslicer-mcp`);
  - variables de entorno;
  - tabla de herramientas con la columna v1/v2;
  - seguridad de impresión;
  - hoja de ruta de la v2;
  - licencia.

  `docs/usage.md`: ejemplos de conversación en español.
- [ ] **Step 2:** Verificación completa: `uv run pytest -q` en local (con PrusaSlicer) → todo pasa, 0 skips de `slicer`. CI verde en GitHub con `gh run watch`.
- [ ] **Step 3:** Prueba manual con Claude Code: `claude mcp add` en local, pedir "lista mis impresoras", "lamina el benchy en la MK4S y dime los riesgos" y "ábrelo en PrusaSlicer"; anotar el resultado en el PR o commit.
- [ ] **Step 4:** Commit `docs: README and usage guide`, `git tag v0.1.0`, `git push --tags` y `gh release create v0.1.0 --notes-file <notas>`.

---

## Después de la v1

El plan de la **v2** (puente dentro de la GUI) se escribe al terminar la v1, en `docs/superpowers/plans/<fecha>-prusaslicer-mcp-v2.md`, tras explorar `deps/PrusaSlicer/src/slic3r/GUI` (`GUI_App`, `Plater`, `MainFrame`) y validar la compilación sin parches en Windows (spec 4.6 y 6).
