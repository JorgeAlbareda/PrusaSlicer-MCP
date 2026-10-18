# Guía de uso (español)

PrusaSlicer-MCP deja que Claude prepare tus impresiones con tu PrusaSlicer y tus perfiles.
Estos son ejemplos de lo que puedes pedirle y de qué herramientas usa por debajo.

## Primeros pasos

> "¿Qué impresoras tengo configuradas en PrusaSlicer?"

Claude llama a `list_printers`. Si no aparece la tuya, configúrala primero en PrusaSlicer
(asistente de configuración) o importa un bundle con `import_profile_bundle`.

> "Lamina `C:\Piezas\soporte.stl` en la Kobra 2 MAX con PLA, calidad 0.20."

Claude hace `list_compatible_profiles` → `select_profiles` → `add_model` → `slice`, y te devuelve
la ruta del G-code, el tiempo, el filamento (mm y g) y el resultado de la **verificación**: la lista
de ajustes comprobados en el G-code. Si PrusaSlicer hubiera usado otra configuración, el laminado
falla en lugar de darte un archivo equivocado.

## Ajustes

> "Ponle un 25 % de relleno y capa de 0.15, y vuelve a laminar."

`set_setting("fill_density", "25%")`, `set_setting("layer_height", "0.15")`, `slice`.
Los cambios son de la sesión; tus perfiles no se tocan.

> "Guarda esto como perfil 'Soportes resistentes'."

`save_profile_as` crea perfiles de usuario que heredan de los seleccionados, sin sobrescribir nada
(salvo que lo pidas) y comprobando con PrusaSlicer que se pueden usar.

## Varias piezas

> "Pon 4 copias del engranaje y 2 del eje, colócalas y dime dónde quedan."

`add_model(..., copies=4)`, `add_model(..., copies=2)`, `arrange_plate`. Para fijar una pieza:
`place_instance(objeto, copia, x, y)`. Antes de laminar se comprueba que todo cabe y nada se solapa.

## Análisis

> "¿Dónde se va el tiempo en esta impresión?"

`analyze_toolpaths`: tiempo y material por tipo (perímetros, relleno, puentes, desplazamientos…).
Los tiempos por capa son estimaciones.

> "¿Ves algún riesgo?"

`find_print_risks`: avisos con su evidencia (warping, voladizos, puentes largos, caudal, límites de
la máquina, capas demasiado rápidas…). `measured` es un límite superado; `heuristic` es un indicio.

> "Ábrelo en PrusaSlicer."

`show_in_slicer` abre el 3MF en tu ventana de PrusaSlicer o el G-code en el visor.

## Impresora en red

> "Súbelo a la Kobra."

`upload_gcode` sube el archivo a la impresora física configurada en PrusaSlicer (OctoPrint,
Moonraker/Klipper o PrusaLink) **sin** empezar a imprimir.

Iniciar, pausar, reanudar o cancelar está **desactivado** salvo que lo actives con
`PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1`. Aun así, siempre te pedirá confirmación.

## Lo que llegará con la v2

Ver los cambios en directo en la ventana de PrusaSlicer, vista previa por capas (`preview_layer`),
altura de capa adaptativa (`set_variable_layer_height`) y ajustes por tramos de altura
(`add_height_range_modifier`).
