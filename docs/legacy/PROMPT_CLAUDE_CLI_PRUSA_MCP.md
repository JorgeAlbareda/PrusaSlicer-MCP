# Especificaciones de Desarrollo: Server MCP para PrusaSlicer 2.6 (Kobra 2 MAX)

## 📌 Contexto del Proyecto
* **Ubicación del Proyecto**: `C:\Users\Jorge\Desarrollo\Prusa Slicer 2.6 MCP`
* **Objetivo**: Desarrollar un servidor **Model Context Protocol (MCP)** para automatizar y controlar el flujo de laminado (*slicing*) de impresiones 3D en la impresora **Anycubic Kobra 2 MAX** usando **PrusaSlicer 2.6**.
* **Impresora Objetivo**: Anycubic Kobra 2 MAX
  * **Volumen útil**: 430 × 430 × 500 mm
  * **Firmware**: Marlin / Kobra OS
  * **Perfil de inicio**: `Kobra2MAX_Standard_PrusaSlicer.ini` (extraído del perfil de fábrica con velocidad base de 230 mm/s y aceleración de 10,000 mm/s²).

---

## 🛠️ FASE 1: Servidor MCP vía CLI Wrapper (`prusa-slicer-console.exe`)

### 🎯 Objetivo de la v1
Crear un servidor MCP funcional en Python utilizando `fastmcp` (o el SDK oficial de MCP) que envuelva la ejecución del ejecutable por línea de comandos de PrusaSlicer (`prusa-slicer-console.exe`), permitiendo a cualquier cliente MCP (Claude Desktop, VS Code, etc.) laminar modelos STL/3MF, modificar perfiles `.ini` y extraer métricas de impresión del GCODE resultante.

### 📐 Estructura de Archivos (Fase 1)
```text
C:\Users\Jorge\Desarrollo\Prusa Slicer 2.6 MCP\
├── profiles\
│   └── Kobra2MAX_Standard_PrusaSlicer.ini
├── src\
│   ├── __init__.py
│   ├── config.py             # Configuración de rutas (exe de PrusaSlicer, carpeta de perfiles)
│   ├── slicer_cli.py         # Subprocess wrapper para prusa-slicer-console.exe
│   ├── profile_manager.py    # Parser y modificador de archivos .ini
│   └── gcode_parser.py       # Extractor de métricas del GCODE resultante
├── server.py                 # Punto de entrada del servidor FastMCP
├── requirements.txt
└── README.md
```

### 📋 Herramientas MCP a Implementar en v1

1. `slice_model(stl_path: str, profile_name: str, output_path: str = None) -> dict`
   * **Descripción**: Lamina un archivo STL/3MF utilizando un perfil `.ini` especificado.
   * **Comando subyacente**: `prusa-slicer-console.exe --slice --load <profile.ini> --output <out.gcode> <model.stl>`
   * **Respuesta**: Estado del proceso, ruta del GCODE generado, tiempo estimado y consumo de filamento.

2. `get_gcode_metrics(gcode_path: str) -> dict`
   * **Descripción**: Analiza los comentarios finales del archivo GCODE generado por PrusaSlicer.
   * **Métricas a extraer**:
     * `; estimated printing time` (tiempo total de impresión).
     * `; filament used [mm]` y `; filament used [g]` (consumo de filamento en longitud y peso).
     * `; total filament cost` (coste estimado si está configurado).
     * Número total de capas y altura de capa.

3. `read_profile_setting(profile_name: str, key: str) -> dict`
   * **Descripción**: Lee un parámetro específico dentro del archivo `.ini` (ej. `top_solid_infill_speed`, `ironing`, `layer_height`).

4. `update_profile_setting(profile_name: str, key: str, value: str, new_profile_name: str = None) -> dict`
   * **Descripción**: Modifica un parámetro dentro de un perfil `.ini` o crea un perfil modificado derivado.

5. `list_available_profiles() -> list[str]`
   * **Descripción**: Lista los perfiles `.ini` disponibles dentro de la carpeta `profiles/`.

---

## ⚡ FASE 2: Integración Íntima y Avanzada (*Deep Integration*)

### 🎯 Objetivo de la v2
Evolucionar el servidor MCP hacia un control bidireccional profundo del motor de laminado, eliminando la dependencia rígida de archivos temporales en disco y ofreciendo capacidades analíticas y de automatización en tiempo real.

### 🔬 Funcionalidades Clave de la v2

1. **Procesamiento de Mallas en Memoria (In-Memory Pipeline)**:
   * Integración mediante C++ bindings (`pybind11` o CFFI con `libslic3r`) o IPC rápido para transferir mallas 3D directamente desde memoria sin I/O de disco.

2. **Inspección Anatómica del GCODE y Toolpath Analytics**:
   * Parser avanzado de código G para mapear los tiempos y aceleraciones reales por tipo de movimiento (perímetros, relleno interno, relleno sólido superior, movimientos de viaje).
   * Identificación automática de zonas críticas con riesgo de *warping*, altas aceleraciones o sobrecalentamiento.

3. **Optimizador Dinámico de Parámetros de Impresión**:
   * Algoritmo de ajuste automático de altura de capa variable según la geometría del modelo.
   * Modificación dinámica de parámetros de refrigeración y velocidad según el área de la capa.

4. **Agrupador y Anidado Automático de Piezas (*Auto-Nesting*)**:
   * Herramienta MCP para posicionar y optimizar la disposición de múltiples objetos dentro del volumen de 430 × 430 mm de la Kobra 2 MAX.

5. **Despacho Directo a la Impresora (OctoPrint / Moonraker / Klipper / Anycubic Cloud)**:
   * Conexión directa mediante API para enviar el GCODE generado a la impresora e iniciar/pausar/monitorear la impresión directamente desde el cliente MCP.

---

## 🚀 Instrucciones de Ejecución para Claude CLI

Ejecuta las siguientes instrucciones dentro de `C:\Users\Jorge\Desarrollo\Prusa Slicer 2.6 MCP`:

1. **Inicialización del Entorno**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install mcp fastmcp click pydantic
   ```
2. **Creación del Proyecto Fase 1**:
   * Generar la estructura de carpetas indicada.
   * Colocar el archivo `Kobra2MAX_Standard_PrusaSlicer.ini` en `profiles/`.
   * Implementar `slicer_cli.py` con detección automática de `prusa-slicer-console.exe` en las rutas estándar de Windows (`C:\Program Files\Prusa3D\PrusaSlicer\`).
   * Implementar `server.py` registrando las 5 herramientas de la Fase 1.
3. **Prueba de Verificación**:
   * Ejecutar el servidor MCP en modo inspección/STDIO y validar la llamada a `list_available_profiles` y `slice_model` con un archivo STL de prueba.
