"""Streaming toolpath analysis of PrusaSlicer G-code.

Moves are classified by ΔE (the change in E, whatever the E mode):
  ΔE > 0 with XY motion -> deposition (attributed to the current ;TYPE:)
  ΔE > 0 without XY     -> unretraction (no path, no flow)
  ΔE < 0                -> retraction (with XY: a wipe, its distance counts as travel)
  ΔE = 0 with XY        -> travel
Times are feedrate estimates (no acceleration model) rescaled to PrusaSlicer's total.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from prusaslicer_mcp.verify import ensure_text_gcode

_WORD_RE = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
UNKNOWN_TYPE = "Unknown"


@dataclass
class TypeStats:
    length_mm: float = 0
    extruded_mm: float = 0
    time_s: float = 0
    moves: int = 0


@dataclass
class LayerStats:
    index: int
    z: float
    height: float
    time_s: float = 0
    time_source: Literal["m73", "estimate"] = "estimate"
    extruded_mm: float = 0
    retractions: int = 0
    by_type: dict[str, TypeStats] = field(default_factory=dict)
    bbox: tuple[float, float, float, float] | None = None
    contact_area_mm2: float = 0
    max_volumetric_mm3s: float = 0
    max_bridge_move_mm: float = 0
    max_vx_mm_s: float = 0
    max_vy_mm_s: float = 0
    max_accel: float = 0


@dataclass
class ToolpathReport:
    by_type: dict[str, TypeStats]
    layers: list[LayerStats]
    travel: TypeStats
    retractions: int
    time_scale: float
    has_type_markers: bool
    unsupported: dict[str, int]
    confidence: Literal["high", "medium", "low"]


def _words(line: str) -> dict[str, float]:
    code = line.split(";", 1)[0]
    return {k.upper(): float(v) for k, v in _WORD_RE.findall(code)}


def _arc_length(x0, y0, x1, y1, i, j, clockwise: bool) -> float:
    cx, cy = x0 + i, y0 + j
    r = math.hypot(i, j)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = (a0 - a1) if clockwise else (a1 - a0)
    sweep %= 2 * math.pi
    if sweep == 0:
        sweep = 2 * math.pi
    return r * sweep


def _filament_diameter_from_config(path: Path) -> float | None:
    from prusaslicer_mcp.verify import read_effective_config

    try:
        value = read_effective_config(path).get("filament_diameter", "")
        return float(value.split(",")[0])
    except Exception:
        return None


def _print_time(path: Path) -> int | None:
    from prusaslicer_mcp.gcode.metrics import _summary, parse_duration

    try:
        return parse_duration(_summary(path).get("estimated printing time (normal mode)", ""))
    except Exception:
        return None


def analyze_toolpaths(path: Path, filament_diameter: float | None = None) -> ToolpathReport:
    path = Path(path)
    ensure_text_gcode(path)
    diameter = filament_diameter or _filament_diameter_from_config(path) or 1.75
    area = math.pi * (diameter / 2) ** 2

    by_type: dict[str, TypeStats] = {}
    travel = TypeStats()
    layers: list[LayerStats] = []
    unsupported: dict[str, int] = {}
    motion_lines = 0
    retractions = 0
    has_markers = False

    x = y = z = e = 0.0
    feed = 0.0
    abs_xyz, abs_e = True, True
    current_type = UNKNOWN_TYPE
    width = 0.0
    accel = 0.0
    last_r: float | None = None
    layer_start_r: float | None = None
    pending_z: float | None = None
    pending_h: float | None = None
    layer: LayerStats | None = None

    def close_layer():
        if layer is not None and layer_start_r is not None and last_r is not None and layer_start_r > last_r:
            layer.time_s = (layer_start_r - last_r) * 60
            layer.time_source = "m73"

    def new_layer():
        nonlocal layer, layer_start_r
        close_layer()
        layer = LayerStats(index=len(layers), z=pending_z if pending_z is not None else z,
                           height=pending_h or 0.0, max_accel=accel)
        layers.append(layer)
        layer_start_r = last_r

    def unsupported_hit(kind: str):
        unsupported[kind] = unsupported.get(kind, 0) + 1

    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line[0] == ";":
                if line.startswith(";TYPE:"):
                    current_type = line[6:].strip()
                    has_markers = True
                elif line.startswith(";LAYER_CHANGE"):
                    pending_z = pending_h = None
                    new_layer()
                elif line.startswith(";Z:"):
                    pending_z = float(line[3:])
                    if layer is not None:
                        layer.z = pending_z
                elif line.startswith(";HEIGHT:"):
                    pending_h = float(line[8:])
                    if layer is not None:
                        layer.height = pending_h
                elif line.startswith(";WIDTH:"):
                    width = float(line[7:])
                continue
            cmd = line.split(None, 1)[0].upper()
            w = _words(line)
            if cmd in ("G0", "G1", "G2", "G3"):
                motion_lines += 1
                nx = w.get("X", 0.0) + (0 if abs_xyz else x) if "X" in w else x
                ny = w.get("Y", 0.0) + (0 if abs_xyz else y) if "Y" in w else y
                nz = w.get("Z", 0.0) + (0 if abs_xyz else z) if "Z" in w else z
                if "F" in w:
                    feed = w["F"]
                de = 0.0
                if "E" in w:
                    de = w["E"] - e if abs_e else w["E"]
                    e = w["E"] if abs_e else e + w["E"]
                dx, dy = nx - x, ny - y
                if cmd in ("G2", "G3"):
                    if "I" in w or "J" in w:
                        xy = _arc_length(x, y, nx, ny, w.get("I", 0.0), w.get("J", 0.0), cmd == "G2")
                    else:
                        unsupported_hit("G2/G3 sin IJ")
                        xy = math.hypot(dx, dy)
                else:
                    xy = math.hypot(dx, dy)
                dist = math.hypot(xy, nz - z)
                t = dist / (feed / 60) if feed > 0 and dist > 0 else (abs(de) / (feed / 60) if feed > 0 else 0.0)
                if layer is None:
                    # start G-code (homing, purge line) before the first layer: not part of the print
                    x, y, z = nx, ny, nz
                    continue
                if t > 0 and xy > 0:
                    layer.max_vx_mm_s = max(layer.max_vx_mm_s, abs(dx) / t)
                    layer.max_vy_mm_s = max(layer.max_vy_mm_s, abs(dy) / t)
                layer.time_s += t if layer.time_source == "estimate" else 0
                if de > 1e-9 and xy > 1e-9:
                    st = by_type.setdefault(current_type, TypeStats())
                    lt = layer.by_type.setdefault(current_type, TypeStats())
                    for s in (st, lt):
                        s.length_mm += xy
                        s.extruded_mm += de
                        s.time_s += t
                        s.moves += 1
                    layer.extruded_mm += de
                    if t > 0:
                        layer.max_volumetric_mm3s = max(layer.max_volumetric_mm3s, de * area / t)
                    if current_type == "Bridge infill":
                        layer.max_bridge_move_mm = max(layer.max_bridge_move_mm, xy)
                    if layer.index == 0:
                        b = layer.bbox or (min(x, nx), min(y, ny), max(x, nx), max(y, ny))
                        layer.bbox = (min(b[0], x, nx), min(b[1], y, ny), max(b[2], x, nx), max(b[3], y, ny))
                        layer.contact_area_mm2 += xy * width
                elif de < -1e-9:
                    retractions += 1
                    layer.retractions += 1
                    if xy > 0:
                        travel.length_mm += xy
                        travel.time_s += t
                        travel.moves += 1
                elif de <= 1e-9 and xy > 1e-9:
                    travel.length_mm += xy
                    travel.time_s += t
                    travel.moves += 1
                x, y, z = nx, ny, nz
            elif cmd == "G90":
                abs_xyz = True
            elif cmd == "G91":
                abs_xyz = False
            elif cmd == "M82":
                abs_e = True
            elif cmd == "M83":
                abs_e = False
            elif cmd == "G92":
                x, y, z, e = w.get("X", x), w.get("Y", y), w.get("Z", z), w.get("E", e)
            elif cmd == "M204":
                value = w.get("S", w.get("P"))
                if value is not None:
                    accel = value
                    if layer is not None:
                        layer.max_accel = max(layer.max_accel, accel)
            elif cmd == "M73":
                if "R" in w:
                    last_r = w["R"]
            elif cmd in ("G10", "G11"):
                unsupported_hit("G10/G11")
            elif cmd == "G20":
                unsupported_hit("G20")
    close_layer()

    raw_total = sum(lay.time_s for lay in layers if lay.time_source == "estimate")
    slicer_total = _print_time(path)
    m73_total = sum(lay.time_s for lay in layers if lay.time_source == "m73")
    scale = 1.0
    if slicer_total and raw_total > 0:
        scale = max(slicer_total - m73_total, 0) / raw_total or 1.0
    for lay in layers:
        if lay.time_source == "estimate":
            lay.time_s *= scale
        for s in lay.by_type.values():
            s.time_s *= scale
    for s in by_type.values():
        s.time_s *= scale
    travel.time_s *= scale

    n_unsupported = sum(unsupported.values())
    if n_unsupported == 0 and has_markers:
        confidence = "high"
    elif n_unsupported <= 0.01 * max(motion_lines, 1):
        confidence = "medium"
    else:
        confidence = "low"
    return ToolpathReport(by_type, layers, travel, retractions, scale, has_markers, unsupported, confidence)
