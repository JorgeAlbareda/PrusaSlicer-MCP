# Pendientes (estado al cerrar la sesión del 2026-10-18)

v1 publicada como **v0.1.0** (motor CLI, 181 tests en Windows con PrusaSlicer 2.9.4 y 2.9.6).

## 1. v2 — PrusaSlicer parcheado con puente en la ventana (spec 4.6)
- [ ] Compilar PrusaSlicer 2.9.6 **sin parches** en Windows (Visual Studio 2022; dependencias 1–2 h la primera vez).
- [ ] Explorar `deps/PrusaSlicer/src/slic3r/GUI` (`GUI_App`, `Plater`, `MainFrame`) y escribir el plan de la v2.
- [ ] Puente mínimo (cargar modelo + laminar), después el resto: `preview_layer`, `set_variable_layer_height`, `add_height_range_modifier`.

## 2. Menores de la revisión final de la v1
Los que más se notan en el uso:
- [ ] `normalize` no canoniza valores `AxB`: `bed_shape` con `100.000x0` da falso fallo de verificación.
- [ ] Clientes con elicitation solo por URL: la herramienta falla en vez de usar el código de confirmación.
- [ ] OctoPrint `start()` no codifica en URL el nombre de archivo (`#`, `?`).
- [ ] Las carpetas de trabajo `<workdir>/<pid>/` no se limpian nunca.

Robustez:
- [ ] Con postprocesado permitido, la limpieza tras timeout puede colgarse (proceso nieto con las tuberías abiertas).
- [ ] Carrera al crear el motor en las primeras llamadas; las herramientas de lectura leen la sesión sin lock.
- [ ] Si falla la comprobación de `save_profile_as`, el preset escrito se queda en disco (sin rollback).
- [ ] `install._read_version` no pone `stdin=DEVNULL`.

Detalles:
- [ ] Las subidas a impresora cargan el archivo entero en memoria.
- [ ] `import_profile_bundle` no convierte en error claro un archivo inexistente.
- [ ] Tiempos por tipo de movimiento incoherentes al mezclar capas con M73 y estimadas.
- [ ] Documentar que `--material-profile` separa nombres por `;`.

## 3. Para Jorge
- [ ] Probar con Claude: `claude mcp add prusaslicer -- uvx --from git+https://github.com/JorgeAlbareda/PrusaSlicer-MCP@v0.1.0 prusaslicer-mcp`.
- [ ] Instalar perfiles en PrusaSlicer (copiar `examples/profiles/kobra2max/` a `%APPDATA%\PrusaSlicer` o usar el asistente).
- [ ] Ajustar densidad y precio reales del PLA (ejemplo: 1.24 g/cm³, 20/kg).
- [ ] ¿La Kobra tiene OctoPrint o Klipper? Sin eso no hay envío por red.

## 4. Mantenimiento
- [ ] Actualizar acciones del CI que usan Node 20 (`checkout`, `cache`, `setup-uv`).
- [ ] macOS y Linux (código portable, sin probar).
