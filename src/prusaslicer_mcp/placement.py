"""Deterministic placement of object instances on a rectangular bed (shelf packing)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from prusaslicer_mcp.errors import PrusaMcpError

Bed = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y


@dataclass
class Footprint:
    object_id: int
    instance: int
    width: float
    depth: float
    center: tuple[float, float] | None
    fixed: bool


def parse_bed_polygon(bed_shape: str) -> list[tuple[float, float]]:
    return [tuple(float(c) for c in p.split("x")) for p in bed_shape.split(",") if p.strip()]


def parse_bed_shape(bed_shape: str) -> Bed:
    points = parse_bed_polygon(bed_shape)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _inside(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray casting; points on the boundary count as inside."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if min(y1, y2) <= y <= max(y1, y2) and min(x1, x2) <= x <= max(x1, x2):
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if abs(cross) < 1e-6:
                return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _in_polygon(f: Footprint, polygon: list[tuple[float, float]] | None) -> bool:
    if not polygon:
        return True
    x0, y0, x1, y1 = _rect(f, 0)
    return all(_inside(c, polygon) for c in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


def _rect(f: Footprint, margin: float) -> tuple[float, float, float, float]:
    cx, cy = f.center
    return (cx - f.width / 2 - margin, cy - f.depth / 2 - margin, cx + f.width / 2 + margin, cy + f.depth / 2 + margin)


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _label(f: Footprint) -> str:
    return f"objeto {f.object_id} copia {f.instance}"


def pack(
    footprints: list[Footprint], bed: Bed, spacing: float = 6.0, polygon: list[tuple[float, float]] | None = None
) -> list[Footprint]:
    """Keep fixed/positioned footprints, place the others in shelves; returns new footprints."""
    result = [replace(f) for f in footprints]
    placed = [f for f in result if f.center is not None]
    todo = sorted((f for f in result if f.center is None), key=lambda f: (-f.depth, -f.width))
    min_x, min_y, max_x, max_y = bed
    half = spacing / 2
    for f in todo:
        if f.width > max_x - min_x or f.depth > max_y - min_y:
            raise PrusaMcpError(f"No caben todas las piezas en la cama: {_label(f)} mide {f.width:.0f}×{f.depth:.0f} mm.")
        y = min_y
        done = False
        while not done and y + f.depth <= max_y + 1e-9:
            x = min_x
            row_step = f.depth + spacing
            while x + f.width <= max_x + 1e-9:
                f.center = (x + f.width / 2, y + f.depth / 2)
                blocker = next((p for p in placed if _overlaps(_rect(f, half), _rect(p, half))), None)
                if blocker is None and _in_polygon(f, polygon):
                    placed.append(f)
                    done = True
                    break
                if blocker is None:  # outside a non-rectangular bed: try further right
                    x += max(spacing, 1.0)
                    continue
                x = _rect(blocker, half)[2] + half
                row_step = min(row_step, _rect(blocker, half)[3] + half - y)
            if not done:
                y += max(row_step, 1.0)
        if not done:
            f.center = None
            raise PrusaMcpError(f"No caben todas las piezas en la cama: no hay hueco para {_label(f)}.")
    if todo and len(todo) == len(result):
        centred = [replace(f) for f in todo]
        _center_group(centred, bed)
        if all(_in_polygon(f, polygon) for f in centred):
            for f, c in zip(todo, centred):
                f.center = c.center
    return result


def _center_group(group: list[Footprint], bed: Bed) -> None:
    """Shift a freely packed group so it sits in the middle of the bed."""
    rects = [_rect(f, 0) for f in group]
    gx = (min(r[0] for r in rects) + max(r[2] for r in rects)) / 2
    gy = (min(r[1] for r in rects) + max(r[3] for r in rects)) / 2
    dx = (bed[0] + bed[2]) / 2 - gx
    dy = (bed[1] + bed[3]) / 2 - gy
    for f in group:
        f.center = (f.center[0] + dx, f.center[1] + dy)


def validate(
    footprints: list[Footprint], bed: Bed, spacing: float = 6.0, polygon: list[tuple[float, float]] | None = None
) -> list[str]:
    problems = []
    half = spacing / 2
    min_x, min_y, max_x, max_y = bed
    located = [f for f in footprints if f.center is not None]
    for f in footprints:
        if f.center is None:
            problems.append(f"{_label(f)} no tiene posición.")
    for f in located:
        r = _rect(f, 0)
        outside_rect = r[0] < min_x - 1e-6 or r[1] < min_y - 1e-6 or r[2] > max_x + 1e-6 or r[3] > max_y + 1e-6
        if outside_rect or not _in_polygon(f, polygon):
            # PrusaSlicer silently drops instances that are not fully on the bed
            problems.append(f"{_label(f)} queda fuera de la cama.")
    for i, a in enumerate(located):
        for b in located[i + 1:]:
            if _overlaps(_rect(a, half), _rect(b, half)):
                problems.append(f"{_label(a)} solapa con {_label(b)} (separación mínima {spacing:g} mm).")
    return problems
