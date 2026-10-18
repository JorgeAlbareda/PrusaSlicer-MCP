"""Summary metrics that PrusaSlicer writes at the end of a G-code file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from prusaslicer_mcp.verify import BEGIN, read_effective_config, read_tail_text

_DURATION_RE = re.compile(r"(\d+)\s*([dhms])")
_UNIT_S = {"d": 86400, "h": 3600, "m": 60, "s": 1}


@dataclass
class GcodeMetrics:
    print_time_s: int | None
    print_time_silent_s: int | None
    filament_mm: float | None
    filament_cm3: float | None
    filament_g: float | None
    cost: float | None
    layer_count: int
    layer_height: float | None
    first_layer_height: float | None
    printer: str | None
    print_profile: str | None
    filaments: list[str] = field(default_factory=list)
    config: dict[str, str] = field(default_factory=dict)


def parse_duration(text: str) -> int | None:
    parts = _DURATION_RE.findall(text or "")
    if not parts:
        return None
    return sum(int(n) * _UNIT_S[u] for n, u in parts)


def _num(value: str | None) -> float | None:
    """Single number, or the sum of a comma-separated list (one value per extruder)."""
    if value is None or value.strip() == "":
        return None
    try:
        return round(sum(float(v) for v in value.split(",")), 6)
    except ValueError:
        return None


def resolve_value(config: dict[str, str], key: str, base_key: str | None = None) -> float | None:
    """Numeric value of a setting; percentages are resolved against `base_key`."""
    raw = config.get(key)
    if raw is None or raw.strip() == "":
        return None
    raw = raw.split(",")[0].strip()
    if raw.endswith("%"):
        if base_key is None:
            return None
        base = resolve_value(config, base_key)
        if base is None:
            return None
        try:
            return base * float(raw[:-1]) / 100
        except ValueError:
            return None
    try:
        return float(raw)
    except ValueError:
        return None


def _summary(gcode: Path) -> dict[str, str]:
    text = read_tail_text(gcode)
    end = text.rfind(BEGIN)
    summary: dict[str, str] = {}
    for line in text[: end if end >= 0 else len(text)].splitlines():
        if line.startswith("; ") and " = " in line:
            key, _, value = line[2:].partition(" = ")
            summary[key.strip()] = value.strip()
    return summary


def _count_layers(gcode: Path) -> int:
    count = 0
    with open(gcode, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(";LAYER_CHANGE"):
                count += 1
    return count


def get_gcode_metrics(path: Path) -> GcodeMetrics:
    path = Path(path)
    config = read_effective_config(path)
    s = _summary(path)
    density = _num(config.get("filament_density"))
    grams = _num(s.get("total filament used [g]") or s.get("filament used [g]"))
    filaments = [f.strip().strip('"') for f in config.get("filament_settings_id", "").split(";") if f.strip()]
    return GcodeMetrics(
        print_time_s=parse_duration(s.get("estimated printing time (normal mode)", "")),
        print_time_silent_s=parse_duration(s.get("estimated printing time (silent mode)", "")),
        filament_mm=_num(s.get("filament used [mm]")),
        filament_cm3=_num(s.get("filament used [cm3]")),
        filament_g=grams if density else None,
        cost=_num(s.get("total filament cost") or s.get("filament cost")),
        layer_count=_count_layers(path),
        layer_height=_num(config.get("layer_height")),
        first_layer_height=_num(config.get("first_layer_height")),
        printer=config.get("printer_settings_id", "").strip('"') or None,
        print_profile=config.get("print_settings_id", "").strip('"') or None,
        filaments=filaments,
        config=config,
    )
