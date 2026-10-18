# Anycubic Kobra 2 MAX — example profiles (PrusaSlicer 2.9)

Corrected, PrusaSlicer 2.9-clean user presets derived from a factory-style bundle:

| Kind | Preset name |
|---|---|
| printer | `Anycubic Kobra 2 MAX` (430 × 430 × 500 mm, 0.4 mm nozzle, Marlin) |
| print | `0.20mm Standard @Kobra2MAX` |
| filament | `Anycubic PLA @Kobra2MAX` (density 1.24 g/cm³, example cost 20/kg — adjust it) |

Fixes applied to the original bundle: relative E distances (matches `M83` + `G92 E0` per layer),
quoting of `compatible_printers_condition` / `printer_notes`, coherent default preset names,
removal of keys PrusaSlicer 2.9 does not know or moved, purge-line comment.

## Install

Copy the three folders (`printer/`, `print/`, `filament/`) into your PrusaSlicer data directory
(Windows: `%APPDATA%\PrusaSlicer`, macOS: `~/Library/Application Support/PrusaSlicer`,
Linux: `~/.config/PrusaSlicer`), then restart PrusaSlicer. Or ask the MCP server to
`import_profile_bundle` the original bundle.
