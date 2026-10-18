# PrusaSlicer-MCP — Documento de diseño

- **Fecha:** 2026-10-18
- **Autor:** Jorge Albareda (con Claude)
- **Estado:** **DEFINITIVA**. Aprobada por Jorge, incluidas las decisiones marcadas **[decisión de Claude]**. Incorpora la revisión externa de ChatGPT/Codex (sección 4.9, que prevalece).

Leyenda: lo marcado **[decisión de Claude]** no lo ha decidido Jorge explícitamente; él delegó esas decisiones y puede revertirlas al revisar.

---

## 1. Qué es y por qué

Un proyecto open source que da a PrusaSlicer una **interfaz MCP** (Model Context Protocol), de modo que un asistente como Claude (Claude Desktop, Claude Code o cualquier cliente MCP) pueda preparar impresiones 3D: cargar modelos, elegir perfiles, cambiar ajustes, laminar, analizar el resultado y mandarlo a la impresora.

El objetivo de fondo es que el usuario le pida a Claude cosas como "lamina esta pieza con menos relleno y dime cuánto tarda" y **lo vea pasar en la ventana de PrusaSlicer abierta**. Eso se consigue en dos etapas:

- **v1 – motor CLI:** el servidor MCP controla el PrusaSlicer **oficial** a través de su línea de comandos (`prusa-slicer-console`). No hay que compilar nada. Lamina en segundo plano y puede abrir el resultado en la ventana de PrusaSlicer o en el visor de G-code.
- **v2 – motor GUI ("integración íntima"):** una versión **propia de PrusaSlicer compilada con parches** que lleva dentro un pequeño servidor local (el "puente"). El mismo servidor MCP habla con ese puente y los cambios se ven **en directo** en la ventana: modelos en la cama, ajustes cambiando, laminado y vista previa por capas.

Contexto de origen: existía un borrador (`PROMPT_CLAUDE_CLI_PRUSA_MCP.md`) centrado en una Anycubic Kobra 2 MAX y PrusaSlicer 2.6. Este documento lo sustituye. La Kobra 2 MAX queda como **impresora de ejemplo y de pruebas**, no como objetivo exclusivo.

## 2. Objetivos, no-objetivos y anti-objetivos

### Objetivos
1. Repositorio público propio `JorgeAlbareda/PrusaSlicer-MCP`, abierto para que otras personas lo usen con **cualquier impresora FFF** y, a la larga, **cualquier sistema operativo**.
2. v1 funcional y probada en **Windows** con el PrusaSlicer 2.9 oficial.
3. v2 con PrusaSlicer 2.9 parcheado y compilado en **Windows**, viéndose en directo en la ventana.
4. **Mismas herramientas MCP en v1 y v2**: pasar a v2 cambia el motor que hay debajo, no la forma de pedir las cosas. Lo que un motor no pueda hacer devuelve un error claro ("requiere el motor GUI (v2)").
5. Análisis útil del G-code: tiempos y material por tipo de movimiento y por capa, y detección de riesgos de impresión.
6. Colocación automática de varias piezas en la cama.
7. Envío a impresoras con API de red (OctoPrint, Moonraker/Klipper, PrusaLink).

### No-objetivos (fuera, al menos por ahora)
- Impresoras de resina (SLA). Solo FFF. **[decisión de Claude]**
- Soporte completo de **varios extrusores, MMU o cambiadores de herramienta** (decisión aprobada por Jorge). El modelo de datos se prepara desde el principio para varios extrusores (filamentos y temperaturas como listas por extrusor y un extrusor asignado por objeto), pero en esta entrega solo se implementa y se prueba con un extrusor. Con un perfil de varios extrusores, el servidor avisa de que no está soportado.
- macOS y Linux en la primera entrega. El código de la v1 se escribe portable (detección de rutas por sistema y nada específico de Windows salvo donde haga falta), pero solo se prueba y se da soporte en Windows. La v2 en otros sistemas queda para más adelante.
- Anycubic Cloud y otras nubes de fabricante sin API pública documentada. La Kobra 2 MAX de serie, por tanto, **no** podrá recibir trabajos directamente salvo que tenga OctoPrint o Klipper delante. **[decisión de Claude]**
- *Bindings* C++/Python (`pybind11`/CFFI) contra `libslic3r` ni un "pipeline en memoria". El borrador original los proponía. El puente dentro de la GUI cubre la necesidad real (ver el resultado en directo) con mucho menos coste. **[decisión de Claude]**
- Sustituir o rediseñar la interfaz de PrusaSlicer.
- Que Claude invente sus propios algoritmos de laminado. Siempre se usa el motor de PrusaSlicer.

### Anti-objetivos (cosas que harían fracasar el proyecto aunque "funcione")
- **Generar G-code incorrecto en silencio.** Se encontró un caso real: PrusaSlicer acepta un `.ini` con formato *bundle* (con secciones `[print:…]`), termina con exit 0 y **lamina con los valores por defecto** (cama de 200×200, 200 °C). Todo laminado debe **verificar la configuración efectiva** que aparece en el G-code contra lo que se pidió, y fallar si no coincide.
- **Empezar una impresión física sin confirmación explícita** del usuario.
- **Estropear la configuración del usuario**: sobrescribir sus perfiles, modificar perfiles de sistema o dejar su `PrusaSlicer.ini` en mal estado.
- **Parches tan invasivos** en el código de Prusa que actualizar a una 2.9.x nueva sea inviable.

## 3. Restricciones

- **Base:** PrusaSlicer **2.9 estable**, fijado al tag `version_2.9.6` (la última estable, del 2026-06-25). El usuario tiene instalada la 2.9.4. **[decisión de Claude]** Se recomienda actualizar la instalación local a 2.9.6 para que la v1 y la v2 usen el mismo motor. La v1 debe funcionar con cualquier 2.9.x y avisar (sin fallar) con otras versiones.
- **Licencia:** PrusaSlicer es **AGPL-3.0**. Como la v2 incluye parches sobre su código y se distribuye compilada, el proyecto entero será **AGPL-3.0**. **[decisión de Claude]**
- **Marca:** "PrusaSlicer" es marca de Prusa Research. El README debe dejar claro que es un proyecto **no oficial y sin afiliación**. Se cambiará el nombre si Prusa lo pide.
- **Repositorio propio, no fork.** PrusaSlicer entra como **git submodule** sin modificar, y los cambios se guardan como **parches en el repositorio** (decidido por Jorge).
- **Primera plataforma: Windows 10/11 x64** (decidido por Jorge).
- **Herramientas detectadas en la máquina de desarrollo:** `gh` autenticado como `JorgeAlbareda`, git 2.53, `uv`, Python 3.11–3.14 (pero `python` no está en el PATH: hay que usar `uv`/`py`) y PrusaSlicer 2.9.4 en `C:\Program Files\Prusa3D\PrusaSlicer\`.

## 4. Lo que ya está decidido sobre el "cómo"

### 4.1 Estructura del repositorio

```text
PrusaSlicer-MCP/
├── deps/PrusaSlicer/          # submodule → prusa3d/PrusaSlicer @ version_2.9.6 (sin modificar)
├── patches/                   # serie de parches (git format-patch) para la v2
├── bridge/                    # código C++ nuevo del puente (lo copian/referencian los parches)
├── src/prusaslicer_mcp/       # servidor MCP en Python
├── tests/                     # pytest: unitarios + integración + extremo a extremo por MCP
│   └── models/                # modelos de prueba
├── examples/profiles/         # perfiles de ejemplo (Kobra 2 MAX corregido y aplanado)
├── scripts/                   # aplicar parches, compilar la v2 en Windows, etc.
├── docs/
├── pyproject.toml
├── LICENSE                    # AGPL-3.0
└── README.md
```

Los detalles finos de esta estructura los decide quien construya.

### 4.2 Servidor MCP

- **Python ≥ 3.11**, SDK oficial **`mcp`** (su `FastMCP` integrado; no se instala además el paquete `fastmcp`). Gestión con **`uv`**. Distribución como paquete `prusaslicer-mcp`, ejecutable con `uvx prusaslicer-mcp`. Transporte **STDIO**. **[decisión de Claude]**
- **Dos motores tras una misma interfaz:** `CliEngine` (v1) y `GuiEngine` (v2). Al arrancar, el servidor usa el `GuiEngine` si detecta el puente en marcha, y si no el `CliEngine`. Se puede forzar uno por configuración.
- **Estado de "sesión" en ambos motores.** La GUI tiene estado: hay piezas en la cama y perfiles seleccionados. Para que las herramientas sean iguales, el `CliEngine` mantiene en el servidor un modelo equivalente: lista de objetos con sus transformaciones, perfiles elegidos y ajustes modificados. Al laminar, ese estado se traduce a una llamada al CLI. El `GuiEngine` refleja el estado real de la ventana.
- **Localizar PrusaSlicer:** rutas estándar de Windows (`Program Files\Prusa3D\PrusaSlicer`), variable de entorno o ajuste del usuario. El código queda preparado para añadir macOS (`/Applications`) y Linux (AppImage, Flatpak) más adelante.
- **Perfiles: los del propio usuario.** Se usan los perfiles que cada persona ya tiene en su PrusaSlicer, de fábrica o propios, a través del *datadir* (en Windows `%APPDATA%\PrusaSlicer`) y de las opciones del CLI 2.9 `--datadir`, `--printer-profile`, `--print-profile`, `--material-profile` y `--query-print-filament-profiles`, que ya se ha comprobado que existen. Opcionalmente se aceptan `.ini` sueltos con `--load`, pero el servidor **rechaza** los *bundles* con secciones (o los aplana explícitamente) en lugar de dejar que PrusaSlicer los ignore.
- **Escritura de perfiles:** solo bajo un nombre nuevo o con confirmación expresa para sobrescribir un perfil de usuario. **Nunca** se modifica un perfil de sistema. Antes de escribir en el *datadir* se hace copia de seguridad. **[decisión de Claude]**

### 4.2.1 Comportamiento del CLI 2.9 comprobado (2026-10-18, con 2.9.4)

- **Perfiles por nombre:** `--datadir D --printer-profile P --print-profile Q --material-profile F` lamina con perfiles del sistema y del usuario. Los tres perfiles son obligatorios. Si un nombre no existe, el error es claro (`Print profile '…' wasn't found.`).
- **Formato del `PrusaSlicer.ini` del datadir:** los modelos instalados van como `[vendor:PrusaResearch]` + `model:MK4S = 0.4` (con el prefijo `model:`). Sin `PrusaSlicer.ini` las consultas fallan con `Configuration wasn't found`. Los bundles de fabricante se copian de `<instalación>/resources/profiles/<Vendor>.ini` a `<datadir>/vendor/`.
- **Consultas:** `--query-printer-models` y `--query-print-filament-profiles` escriben JSON (`-o archivo`). Ojo: algunos nombres de variante salen como número JSON (`"name": 0.4`).
- **Prioridad de configuración:** las claves en línea de comandos (`--fill-density 40%`) pisan a los `--load`, y estos pisan a los perfiles. Los cambios de la sesión se pasan como un `.ini` temporal con `--load` después de los perfiles. Comprobado que funciona.
- **G-code binario:** los perfiles Prusa MK4/MK4S/XL/MINI generan `.bgcode` (cabecera `GCDE`). Con `--no-binary-gcode` sale texto. **[decisión de Claude]** La v1 genera siempre G-code de texto, porque el análisis lo necesita. Exportar binario para impresoras Prusa queda como opción futura.
- **Marcas de tipo:** `;TYPE:…`, `;LAYER_CHANGE`, `;Z:`, `;HEIGHT:` y `;WIDTH:` aparecen siempre, aunque `gcode_comments = 0`.
- **Avisos que no son errores:** al cargar perfiles antiguos aparecen líneas `[error] … contains the following incorrect keys: … which were removed`. No impiden laminar y se clasifican como avisos. PrusaSlicer también escribe avisos propios (`Print warning: Detected print stability issues…`), que se devuelven al usuario.
- **Varios objetos:** las transformaciones del CLI (`--rotate`, `--scale`, `--center`) se aplican a todos los modelos de la llamada. Para transformar cada objeto por separado, cada uno se exporta a un 3MF intermedio con sus transformaciones, y luego se laminan juntos con `--merge` (colocación automática) o `--merge --dont-arrange` (mantiene posiciones). Comprobado que funciona.
- **Modelos incluidos:** PrusaSlicer trae `resources/shapes/` (3DBenchy, cubo, cilindro, toro, tornillo M3, etc.) además de `tests/data`.
- **Binarios oficiales 2.9.6:** `PrusaSlicer-2.9.6.zip` (Windows, portable) en GitHub Releases, útil para CI.

### 4.3 Catálogo de herramientas MCP

Los nombres y parámetros exactos los fija quien construya. Esta es la cobertura funcional. "v1/v2" indica qué motor la soporta.

| Grupo | Herramienta (orientativa) | v1 | v2 | Notas |
|---|---|---|---|---|
| Info | `get_slicer_info` | ✓ | ✓ | versión, ruta, datadir, motor activo |
| Perfiles | `list_printers`, `list_compatible_profiles` | ✓ | ✓ | v1 vía `--query-print-filament-profiles` |
| Perfiles | `select_profiles(printer, print, filament)` | ✓ | ✓ | v2: cambia la selección en la ventana |
| Ajustes | `get_setting`, `set_setting` | ✓ | ✓ | cambios temporales sobre la sesión |
| Ajustes | `save_profile_as` | ✓ | ✓ | ver reglas de escritura de 4.2 |
| Cama | `add_model`, `list_objects`, `remove_object`, `clear_plate` | ✓ | ✓ | STL, 3MF, OBJ, STEP (lo que acepte PrusaSlicer) |
| Cama | `transform_object` (mover, rotar, escalar, copias) | ✓ | ✓ | v1: `--rotate`, `--scale`, `--center`, `--duplicate`… |
| Cama | `arrange_plate` | ✓ | ✓ | colocación automática; v1 con el arrange del CLI (`--merge`), v2 con el de la GUI |
| Laminado | `slice` | ✓ | ✓ | devuelve ruta del G-code, métricas y verificación |
| Laminado | `export_3mf` | ✓ | ✓ | |
| Optimización | `set_variable_layer_height(object, modo adaptativo, calidad)` | ✗ | ✓ | usa la altura de capa adaptativa de PrusaSlicer |
| Optimización | `add_height_range_modifier(object, z_desde, z_hasta, ajustes)` | ✗ (o vía 3MF si es viable) | ✓ | cambiar velocidad, ventilador, relleno, etc. por tramos de altura |
| Análisis | `get_gcode_metrics` | ✓ | ✓ | ver 4.4 |
| Análisis | `analyze_toolpaths` | ✓ | ✓ | ver 4.4 |
| Análisis | `find_print_risks` | ✓ | ✓ | ver 4.4 |
| Ver | `show_in_slicer` | ✓ | ✓ | v1: abre el 3MF/G-code en la ventana existente (`--single-instance`) o en el visor de G-code; v2: no hace falta, se ve en directo |
| Ver | `preview_layer(n)` | ✗ | ✓ | lleva la vista previa a la capa n |
| Impresora | `list_print_hosts` | ✓ | ✓ | lee las impresoras físicas configuradas en PrusaSlicer (`physical_printer/`) |
| Impresora | `upload_gcode(host, path, start=false)` | ✓ | ✓ | |
| Impresora | `get_printer_status`, `pause_print`, `resume_print`, `cancel_print` | ✓ | ✓ | |

El acceso a impresoras lo implementa el servidor MCP en Python, hablando directamente con la API HTTP de **OctoPrint**, **Moonraker (Klipper)** y **PrusaLink**, con las credenciales que el usuario ya guardó en PrusaSlicer. No depende del motor. **[decisión de Claude]**

**Reglas de seguridad para la impresora (decisión aprobada por Jorge):** iniciar, pausar, reanudar y cancelar requieren confirmación **del humano**, no de un parámetro que rellena el modelo.
- Si el cliente MCP soporta *elicitation*, el servidor pregunta directamente al usuario ("¿Iniciar `pieza.gcode` en `Kobra (OctoPrint)`? sí/no").
- Si no la soporta, se usa un flujo en **dos pasos**. La primera llamada no actúa: devuelve un resumen y un código de un solo uso que caduca a los 2 minutos, con instrucciones al modelo de pedir confirmación al usuario. La segunda llamada, con ese código, ejecuta.
- Las herramientas se marcan además como destructivas en las anotaciones MCP.
- Subir un archivo sin iniciar la impresión no requiere confirmación.

### 4.4 Análisis del G-code (qué es y para qué sirve)

PrusaSlicer marca cada tramo del G-code con su tipo de movimiento (`;TYPE:Perimeter`, `;TYPE:External perimeter`, `;TYPE:Internal infill`, `;TYPE:Solid infill`, `;TYPE:Top solid infill`, `;TYPE:Bridge infill`, `;TYPE:Overhang perimeter`, `;TYPE:Support material`, `;TYPE:Skirt/Brim`, etc.) y con el ancho y alto de extrusión. Leyendo esas marcas se puede explicar **dónde se va el tiempo y el material** y **dónde puede fallar la impresión**. Todo esto es Python puro, así que funciona igual en v1 y v2.

- **`get_gcode_metrics`:** lo que PrusaSlicer escribe al final del G-code (tiempo estimado normal y silencioso; filamento en mm, cm³ y g; coste; número de capas; altura de capa; perfiles usados) más la **configuración efectiva** completa.
- **`analyze_toolpaths`:** por tipo de movimiento y por capa: longitud recorrida, filamento, tiempo aproximado, velocidad media y número de retracciones y desplazamientos. Las marcas solo existen si están activos `gcode_comments` o las etiquetas de tipo; si faltan, el análisis lo indica.
- **`find_print_risks`:** avisos con capa, zona y motivo. **[decisión de Claude]** Lista inicial:
  - **Capas demasiado rápidas** (tiempo de capa por debajo del umbral de refrigeración): plástico blando, deformación en puntas.
  - **Riesgo de warping:** primera capa con mucha superficie o pegada a los bordes de la cama, sobre todo con materiales sensibles (ABS, ASA, PC, PETG grande) y sin brim.
  - **Voladizos y puentes largos:** capas con mucho `Overhang perimeter` o `Bridge infill`, o con puentes muy largos.
  - **Caudal volumétrico** por encima del máximo del filamento o del hotend: posible subextrusión a altas velocidades.
  - **Aceleraciones o velocidades** pedidas por encima de los límites de la máquina.
  - **Muchas retracciones** en poco recorrido: riesgo de *stringing* o de "comerse" el filamento.
  - **Primera capa** más rápida o más fina de lo recomendable para el perfil.

  Los umbrales deben ser configurables y documentados. Los valores iniciales concretos los decide quien construya, basándose en los propios ajustes del perfil cuando existan (por ejemplo `slowdown_below_layer_time` o `filament_max_volumetric_speed`).

### 4.5 Verificación del laminado (obligatoria)

Tras cada `slice`, el servidor lee la configuración efectiva del G-code (`; clave = valor` al final) y la compara con lo pedido: perfil de impresora (`printer_model`, `bed_shape`), temperaturas, altura de capa y cada ajuste cambiado en la sesión. Si algo no coincide, `slice` **falla** con la lista de diferencias. También se recogen y devuelven los avisos y errores que PrusaSlicer escribe por consola (por ejemplo `"G92 E0" … incompatible with absolute extruder addressing`).

### 4.6 v2: el puente dentro de PrusaSlicer

- **Qué es:** código C++ nuevo dentro de la GUI de PrusaSlicer que abre un servidor **solo en `127.0.0.1`**. Recibe órdenes del servidor MCP (JSON-RPC o similar) y las ejecuta sobre la propia aplicación (cargar, transformar, colocar, cambiar ajustes, laminar, vista previa, exportar).
- **Seguridad:** el puente está **desactivado por defecto**. Se activa con una opción de arranque (por ejemplo `--mcp-bridge`) o un ajuste. Usa un token aleatorio por sesión, guardado en un archivo del *datadir* que lee el servidor MCP. Nunca escucha fuera de localhost.
- **Hilos:** toda acción sobre la interfaz se ejecuta en el hilo principal de wxWidgets (por ejemplo con `CallAfter`). El laminado en segundo plano de PrusaSlicer se respeta, y el puente informa de cuándo ha terminado.
- **Parches mínimos:** el grueso del código vive en archivos nuevos (`bridge/`). Los parches sobre los archivos de Prusa se limitan a "enganches": registrar el puente al arrancar, añadirlo al CMake, la opción de línea de comandos y la exposición de las funciones de `Plater` necesarias. Objetivo: que llevar los parches a una 2.9.x nueva sea cuestión de horas, no de días.
- **Compilación en Windows:** se sigue el procedimiento oficial de PrusaSlicer para Windows (Visual Studio 2022, dependencias con su script de *deps*) envuelto en un script del repositorio que aplica los parches y compila. La primera compilación de dependencias es larga (una o varias horas); hay que documentarlo.
- **Distribución (decisión aprobada por Jorge):** al principio la v2 se distribuye **solo como script de compilación** documentado. Publicar un binario en GitHub Releases (zip, con su oferta de código fuente AGPL) queda para cuando la v2 esté estable; no forma parte de esta entrega.
- **Identidad:** el ejecutable compilado debe distinguirse del oficial (nombre o título de ventana, por ejemplo "PrusaSlicer-MCP") y usar por defecto el mismo *datadir* del usuario para ver sus perfiles. **[decisión de Claude]** Riesgo: si el usuario tiene abiertos a la vez el oficial y el parcheado, ambos escriben `PrusaSlicer.ini`. Hay que documentarlo; quien construya puede optar por un *datadir* separado que importe los perfiles.

### 4.7 Pruebas

- **Criterio de "v1 terminada"** (decidido por Jorge): pasa una batería de pruebas con **STL públicos de test**.
- **Modelos:** los de prueba del propio PrusaSlicer (`deps/PrusaSlicer/tests/data`: `20mm_cube.obj`, `bridge.obj`, `overhang.obj`, `U_overhang.obj`, `cube_with_hole.obj`, `pyramid.obj`, `frog_legs.obj`, etc., AGPL-3.0) y, si su licencia lo permite, clásicos como el 3DBenchy y el cubo de calibración XYZ. Se debe comprobar y anotar la licencia de cada modelo que se incluya.
- **Qué se prueba:** que el laminado sale bien con un perfil concreto y **la verificación de 4.5** lo confirma; que las métricas son coherentes; que cambiar un ajuste cambia el resultado; que los errores son claros (bundle, perfil incompatible, modelo fuera de la cama, ejecutable no encontrado); que `analyze_toolpaths` y `find_print_risks` dan resultados esperados con modelos pensados para ello (por ejemplo, el de puentes produce aviso de puente); y una **prueba de extremo a extremo** que arranca el servidor por STDIO y llama a las herramientas como un cliente MCP.
- **Perfiles de prueba:** perfiles de sistema de PrusaSlicer (por ejemplo Prusa MK4) usando un *datadir* temporal de prueba (nunca el del usuario), más el perfil de ejemplo de la Kobra 2 MAX.
- **Impresoras en pruebas:** contra servidores simulados (mocks) de OctoPrint, Moonraker y PrusaLink, nunca contra una impresora real.
- **CI:** GitHub Actions en **Windows**, instalando el PrusaSlicer 2.9.6 oficial. La compilación de la v2 en CI es opcional y de lanzamiento manual por su coste. **[decisión de Claude]**
- **v2:** las mismas pruebas de herramientas se ejecutan contra el `GuiEngine` con el PrusaSlicer parcheado abierto. Además, una comprobación manual documentada: "se ve en la ventana".

### 4.8 Perfil de ejemplo Kobra 2 MAX

El `.ini` original tiene errores que se corrigen al incluirlo en `examples/profiles/`:
- **Formato:** se convierte de *bundle* a config plano o a perfiles de usuario instalables.
- **`use_relative_e_distances = 1`**, coherente con el `M83` del start G-code y con el `G92 E0` por capa. Sin este cambio PrusaSlicer se niega a laminar.
- **Comillas rotas:** se arreglan `printer_model==""KOBRA2MAX` y `printer_notes`.
- **Nombres de preset por defecto** coherentes con los nombres reales.
- **Claves inválidas eliminadas:** `Hostname`, `post_process_enable`.
- **Filamento PLA:** densidad 1.24 g/cm³ y coste de ejemplo. Son valores de ejemplo y el usuario los ajusta. **[decisión de Claude]**
- **Purga del start G-code:** se corrige el comentario (dice 25 mm y extruye 40).

### 4.9 Ajustes tras la revisión externa (ChatGPT/Codex, 2026-10-18)

Se incorporaron estos puntos de la revisión, cada uno con la solución más simple que lo resuelve. Esta sección **prevalece** sobre lo anterior si hay contradicción.

1. **Control físico de la impresora desactivado por defecto.** El modelo puede devolver él solo el código de confirmación, y algunos clientes responden la *elicitation* sin preguntar al humano. Por eso iniciar, pausar, reanudar y cancelar solo están disponibles si el **usuario** lo activa en la configuración del servidor (`PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1`), que es un canal que el modelo no controla. Con eso activado sigue aplicando la confirmación de 4.3. La documentación dice claramente que la confirmación en dos pasos depende del cliente. El código queda ligado a la impresora **y** al trabajo actual (nombre o id del trabajo leído del estado), así que una aprobación no sirve para otro trabajo. Subir archivos sigue permitido siempre.
2. **Verificación honesta.** `slice` devuelve un bloque `verification` con `checked_keys` (lo que se comprobó), `mismatches` y `ok`. Siempre se comprueba esto:
   - los identificadores de perfil;
   - todos los ajustes cambiados en la sesión;
   - las **claves críticas** que existan en la fuente de la configuración (`bed_shape`, `nozzle_diameter`, `filament_diameter`, `temperature`, `first_layer_temperature`, `bed_temperature`, `first_layer_bed_temperature`, `layer_height`, `first_layer_height`, `gcode_flavor`, `printer_model`, `use_relative_e_distances`).

   Para perfiles con nombre, los valores esperados de las claves críticas salen de leer los `.ini` de usuario del datadir cuando el perfil es de usuario. Si el perfil es de sistema, salen de su sección en el bundle del fabricante, resolviendo `inherits`. Si no se pueden resolver, la clave se lista en `unchecked_keys`. La documentación aclara que esto demuestra que se usó la configuración pedida, no que el G-code sea seguro.
3. **Postprocesado externo bloqueado.** PrusaSlicer ejecuta el programa indicado en `post_process` después de exportar. Por defecto el servidor fuerza `post_process =` (vacío) en el `.ini` de overrides de cada laminado, rechaza `set_setting("post_process", …)` y lo elimina al importar bundles. Se permite solo con `PRUSASLICER_MCP_ALLOW_POST_PROCESS=1`. Una prueba garantiza que un script configurado **no** se ejecuta.
4. **El motor es dueño del estado.** Todas las herramientas que cambian algo (perfiles, ajustes, modelos, transformaciones, colocación) pasan por métodos del `Engine`; ninguna toca la `Session` directamente. El `CliEngine` guarda la `Session` dentro. El `GuiEngine` (v2) aplicará cada cambio en la ventana y la ventana será la fuente de verdad, de modo que `get_plate()` refleja también lo que el usuario cambie a mano. Cada cambio se confirma al devolver la herramienta.
5. **Herencia en bundles.** Al importar, `inherits` se resuelve dentro del propio bundle aplanando de forma recursiva (con detección de ciclos). Si el padre no está en el bundle, se mantiene `inherits` y se avisa. Hay una prueba con un hijo cuyos valores solo existen en el padre.
6. **Colocación determinista hecha por el servidor.** No se usa el *arrange* del CLI.
   - Cada copia es una instancia con su propia posición.
   - `arrange_plate` calcula las posiciones con un empaquetado simple de rectángulos: la huella XY de cada instancia, sacada con `--info` tras transformar, más la separación (`duplicate_distance` del perfil, o 6 mm). Devuelve las posiciones.
   - Las instancias sin posición se colocan automáticamente alrededor de las fijas.
   - Antes de laminar se valida que todas caben en la cama y no se solapan, con margen. Si no, el error es claro.
   - Al laminar siempre se usa `--dont-arrange` con las posiciones resueltas.
7. **Análisis del G-code con máquina de estados.** La clasificación usa **ΔE** (diferencia respecto a la E anterior en modo absoluto, o el valor en modo relativo):
   - ΔE > 0 con XY → deposición;
   - ΔE > 0 sin XY → des-retracción;
   - ΔE < 0 → retracción (con XY, retracción con limpieza);
   - ΔE = 0 → viaje.

   Las construcciones no soportadas (`G10`/`G11` de retracción por firmware, `G2`/`G3` sin I/J, unidades en pulgadas `G20`) se cuentan en `unsupported` y bajan `confidence` (`high`/`medium`/`low`), en lugar de dar cifras falsas.
8. **Tiempos por capa como estimación.** Los tiempos por capa son estimaciones por velocidad, reescaladas al total de PrusaSlicer, y se etiquetan como aproximados. Si el G-code trae marcas `M73` de tiempo restante, se usan por capa porque son más fiables. Los avisos de capa demasiado rápida que se basan en la estimación tienen severidad `info` y llevan la nota.
9. **Reglas de riesgo con evidencias.** Cada `Risk` lleva `evidence` (valores medidos y umbral) y `basis` (`measured` para un límite superado, `heuristic` para un indicio).
   - **Caudal volumétrico:** se usa el **más estricto** de los límites positivos.
   - **Velocidad:** se compara **por eje**, con las componentes vx y vy, contra `machine_max_feedrate_x/y`.
   - **Aceleración:** se toma el **máximo** de la capa, no el último valor.
   - **Warping:** el área de contacto de la primera capa se estima como Σ(longitud × ancho) de las extrusiones. El bbox solo se usa para ver la cercanía al borde.
   - **Altura de capa:** se elimina la regla "altura < ½ boquilla".
   - **Porcentajes:** los ajustes en `%` se resuelven antes de comparar (por ejemplo `first_layer_speed`).
   - **Falsos positivos:** se prueban igual que las detecciones.
10. **Hosts.**
    - **PrusaLink:** la cabecera es `Overwrite: ?0` (no `Overwrite-File`) y no se sobrescribe por defecto. El almacenamiento se descubre con `GET /api/v1/storage` o se configura.
    - **Subida:** `upload()` devuelve la ruta o identificador remoto real, y `start` usa ese valor.
11. **Concurrencia.**
    - Cada laminado trabaja sobre una **copia inmutable** de la sesión y en una carpeta propia (`<workdir>/<pid>/<uuid>/`).
    - Los cambios de estado se serializan con un lock.
    - El CLI y el HTTP se ejecutan fuera del bucle de eventos (`anyio.to_thread`) para que el servidor siga respondiendo.
    - El G-code se mueve a su ruta final **solo si la verificación pasa**.
12. **Perfiles guardados válidos y CI estricto.**
    - `save_profile_as` reparte cada clave en print, filament o printer según las listas oficiales de PrusaSlicer (`s_Preset_*_options` de `Preset.cpp`). Un script del repo las extrae del submódulo a `preset_keys.json`.
    - La escritura es atómica (archivo temporal + renombrado).
    - Se comprueba el resultado con PrusaSlicer, cargando el preset guardado y laminando.
    - En CI, `PRUSASLICER_REQUIRE=1` convierte en fallo la falta de PrusaSlicer, en lugar de omitir las pruebas.

Descartado por complejidad: cambiar la estrategia del puente de la v2 o añadir un canal de aprobación propio (por ejemplo una ventana local de confirmación). El punto 1 cubre el riesgo con mucho menos coste.

## 5. Lo que queda a criterio de quien construya

- Nombres y firmas exactas de las herramientas MCP, y formato de las respuestas.
- Protocolo concreto del puente (JSON-RPC sobre HTTP, WebSocket o TCP plano) y su esquema.
- Cómo mapea el `CliEngine` el estado de sesión a argumentos del CLI. Por ejemplo, si genera un 3MF intermedio o pasa transformaciones por argumentos.
- Umbrales iniciales de `find_print_risks`.
- Organización interna del paquete Python y de los parches.
- Si `add_height_range_modifier` es viable en v1 vía 3MF.
- Detalles del script de compilación y de la caché de dependencias.

## 6. Orden de trabajo sugerido

1. Crear el repositorio público, la licencia, el README, el submódulo fijado a `version_2.9.6` y el esqueleto del paquete.
2. v1: localización de PrusaSlicer, perfiles, sesión y `slice` con verificación. Luego métricas y análisis, colocación en cama, `show_in_slicer` e impresoras. Pruebas y CI en paralelo.
3. Publicar la v1 como versión 0.1.
4. v2: compilar PrusaSlicer 2.9.6 **sin parches** en Windows (validar la cadena de compilación), después el puente mínimo (cargar modelo y laminar) y después el resto de herramientas.
5. Más adelante: macOS y Linux.
