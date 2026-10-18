"""Generate src/prusaslicer_mcp/data/preset_keys.json from the PrusaSlicer submodule.

Maps every config key to the preset kind it belongs to (print / filament / printer),
using the official lists in libslic3r/Preset.cpp and libslic3r/PrintConfig.cpp.

Usage: python scripts/gen_preset_keys.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBSLIC3R = ROOT / "deps" / "PrusaSlicer" / "src" / "libslic3r"
OUT = ROOT / "src" / "prusaslicer_mcp" / "data" / "preset_keys.json"

# Shared bookkeeping keys that exist in every preset kind.
SHARED = {"inherits", "compatible_printers", "compatible_printers_condition"}


def _block(source: str, start_pattern: str) -> list[str]:
    m = re.search(start_pattern + r"\s*\{(.*?)\};", source, re.S)
    if not m:
        raise SystemExit(f"Pattern not found: {start_pattern}")
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return re.findall(r'"([^"]+)"', body)


def main() -> None:
    preset = (LIBSLIC3R / "Preset.cpp").read_text(encoding="utf-8")
    config = (LIBSLIC3R / "PrintConfig.cpp").read_text(encoding="utf-8")
    kinds = {
        "print": _block(preset, r"static std::vector<std::string> s_Preset_print_options"),
        "filament": _block(preset, r"static std::vector<std::string> s_Preset_filament_options"),
        "printer": _block(preset, r"static std::vector<std::string> s_Preset_printer_options")
        + _block(preset, r"static std::vector<std::string> s_Preset_machine_limits_options")
        + _block(config, r"m_extruder_option_keys\s*="),
    }
    mapping: dict[str, str] = {}
    for kind, keys in kinds.items():
        for key in keys:
            if key not in SHARED:
                mapping.setdefault(key, kind)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sorted(mapping.items())), indent=1) + "\n", encoding="utf-8")
    print(f"{len(mapping)} keys -> {OUT}")


if __name__ == "__main__":
    main()
