"""Print-risk detection on top of a ToolpathReport.

Each risk says whether it is a measured limit violation or a heuristic hint, and carries
the evidence (measured values and the threshold) that triggered it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from prusaslicer_mcp.gcode.metrics import resolve_value
from prusaslicer_mcp.gcode.toolpaths import ToolpathReport
from prusaslicer_mcp.placement import parse_bed_shape

Severity = Literal["info", "warning", "high"]
_RANK = {"high": 0, "warning": 1, "info": 2}
_PERIMETERS = ("Perimeter", "External perimeter", "Overhang perimeter")


@dataclass
class Risk:
    kind: str
    severity: Severity
    basis: Literal["measured", "heuristic"]
    layers: tuple[int, int] | None
    message: str
    evidence: dict[str, float | str] = field(default_factory=dict)


@dataclass
class RiskThresholds:
    short_layer_s: float | None = None
    warp_materials: tuple[str, ...] = ("ABS", "ASA", "PC", "PA", "NYLON", "PP")
    warp_contact_cm2: float = 100.0
    bed_edge_margin_mm: float = 5.0
    overhang_fraction: float = 0.25
    bridge_move_mm: float = 25.0
    max_volumetric_mm3s: float | None = None
    retractions_per_layer: int = 60
    first_layer_speed_mm_s: float = 60.0


_MESSAGES = {
    "short_layer_time": "Capas muy rápidas ({value_s:.1f} s < {threshold_s:g} s): el plástico puede no enfriar bien.",
    "overhangs": "Mucho voladizo en el perímetro ({fraction:.0%} > {threshold:.0%}).",
    "long_bridge": "Puente largo de {length_mm:.1f} mm (umbral {threshold_mm:g} mm): puede combarse.",
    "volumetric_flow": "Caudal de {flow_mm3s:.1f} mm³/s por encima del límite de {limit_mm3s:g} mm³/s: posible subextrusión.",
    "retractions": "{count:g} retracciones en una capa (umbral {threshold:g}): riesgo de hilos o de desgastar el filamento.",
}


def _f(config: dict[str, str], key: str) -> float | None:
    return resolve_value(config, key)


def _volumetric_limit(config: dict[str, str], thresholds: RiskThresholds) -> float | None:
    if thresholds.max_volumetric_mm3s is not None:
        return thresholds.max_volumetric_mm3s
    limits = [v for v in (_f(config, "filament_max_volumetric_speed"), _f(config, "max_volumetric_speed")) if v and v > 0]
    return min(limits) if limits else None


def _per_layer(report: ToolpathReport, config: dict[str, str], t: RiskThresholds) -> list[Risk]:
    found: list[Risk] = []
    short = t.short_layer_s if t.short_layer_s is not None else (_f(config, "slowdown_below_layer_time") or 5.0)
    vol_limit = _volumetric_limit(config, t)
    limits_on = config.get("machine_limits_usage", "") != "ignore"
    max_vx, max_vy = _f(config, "machine_max_feedrate_x"), _f(config, "machine_max_feedrate_y")
    max_acc = _f(config, "machine_max_acceleration_extruding")

    for lay in report.layers:
        span = (lay.index, lay.index)
        if lay.index > 0 and lay.extruded_mm >= 0 and 0 < lay.time_s < short:
            estimate = lay.time_source == "estimate"
            found.append(Risk("short_layer_time", "info" if estimate else "warning", "heuristic", span, "",
                              {"value_s": round(lay.time_s, 2), "threshold_s": short,
                               "time_source": lay.time_source}))
        perim = sum(lay.by_type[k].length_mm for k in _PERIMETERS if k in lay.by_type)
        over = lay.by_type.get("Overhang perimeter")
        if over and perim > 0 and over.length_mm / perim > t.overhang_fraction:
            found.append(Risk("overhangs", "warning", "heuristic", span, "",
                              {"fraction": round(over.length_mm / perim, 4), "threshold": t.overhang_fraction}))
        if lay.max_bridge_move_mm > t.bridge_move_mm:
            found.append(Risk("long_bridge", "warning", "measured", span, "",
                              {"length_mm": round(lay.max_bridge_move_mm, 2), "threshold_mm": t.bridge_move_mm}))
        if vol_limit and lay.max_volumetric_mm3s > vol_limit:
            found.append(Risk("volumetric_flow", "high", "measured", span, "",
                              {"flow_mm3s": round(lay.max_volumetric_mm3s, 2), "limit_mm3s": vol_limit}))
        if limits_on:
            ev: dict[str, float | str] = {}
            if max_vx and lay.max_vx_mm_s > max_vx + 1e-6:
                ev.update(max_vx_mm_s=round(lay.max_vx_mm_s, 1), limit_x_mm_s=max_vx)
            if max_vy and lay.max_vy_mm_s > max_vy + 1e-6:
                ev.update(max_vy_mm_s=round(lay.max_vy_mm_s, 1), limit_y_mm_s=max_vy)
            if max_acc and lay.max_accel > max_acc + 1e-6:
                ev.update(max_accel=lay.max_accel, limit_accel=max_acc)
            if ev:
                found.append(Risk("machine_limits", "warning", "measured", span, "", ev))
        if lay.retractions > t.retractions_per_layer:
            found.append(Risk("retractions", "info", "heuristic", span, "",
                              {"count": lay.retractions, "threshold": t.retractions_per_layer}))
    return found


def _group(risks: list[Risk]) -> list[Risk]:
    grouped: list[Risk] = []
    last: dict[tuple[str, str], Risk] = {}
    for r in risks:
        key = (r.kind, r.severity)
        prev = last.get(key)
        if prev and prev.layers and r.layers and r.layers[0] == prev.layers[1] + 1:
            prev.layers = (prev.layers[0], r.layers[1])
            for k, v in r.evidence.items():
                if isinstance(v, (int, float)) and isinstance(prev.evidence.get(k), (int, float)):
                    worse = min if k == "value_s" else max
                    prev.evidence[k] = worse(prev.evidence[k], v)
            continue
        grouped.append(r)
        last[key] = r
    return grouped


def _layers_text(layers: tuple[int, int] | None) -> str:
    if not layers:
        return ""
    a, b = layers
    return f"Capa {a}: " if a == b else f"Capas {a}–{b}: "


def _message(r: Risk) -> str:
    if r.kind == "machine_limits":
        parts = []
        if "max_vx_mm_s" in r.evidence:
            parts.append(f"X a {r.evidence['max_vx_mm_s']} mm/s (máx. {r.evidence['limit_x_mm_s']:g})")
        if "max_vy_mm_s" in r.evidence:
            parts.append(f"Y a {r.evidence['max_vy_mm_s']} mm/s (máx. {r.evidence['limit_y_mm_s']:g})")
        if "max_accel" in r.evidence:
            parts.append(f"aceleración {r.evidence['max_accel']:g} (máx. {r.evidence['limit_accel']:g})")
        body = "Por encima de los límites de la máquina: " + ", ".join(parts) + "."
    else:
        body = _MESSAGES[r.kind].format(**r.evidence)
    if r.kind == "short_layer_time" and r.evidence.get("time_source") == "estimate":
        body += " (estimación aproximada del tiempo por capa)"
    return _layers_text(r.layers) + body


def find_print_risks(
    report: ToolpathReport, config: dict[str, str], thresholds: RiskThresholds | None = None
) -> list[Risk]:
    t = thresholds or RiskThresholds()
    risks = _group(_per_layer(report, config, t))
    for r in risks:
        r.message = _message(r)

    first = report.layers[0] if report.layers else None
    if first is not None:
        material = config.get("filament_type", "").split(";")[0].strip('"').upper()
        brim = _f(config, "brim_width") or 0
        area_cm2 = first.contact_area_mm2 / 100
        if material in t.warp_materials and brim == 0 and area_cm2 >= t.warp_contact_cm2:
            risks.append(Risk("warping_risk", "high", "heuristic", (0, 0),
                              f"Capa 0: {area_cm2:.0f} cm² de contacto en {material} sin brim: riesgo alto de "
                              "despegue (warping). Considera brim o una cama/cerramiento más caliente.",
                              {"contact_cm2": round(area_cm2, 1), "threshold_cm2": t.warp_contact_cm2, "material": material}))
        if first.bbox and config.get("bed_shape"):
            bx0, by0, bx1, by1 = parse_bed_shape(config["bed_shape"])
            x0, y0, x1, y1 = first.bbox
            gap = min(x0 - bx0, y0 - by0, bx1 - x1, by1 - y1)
            if gap < t.bed_edge_margin_mm:
                risks.append(Risk("warping_risk", "warning", "heuristic", (0, 0),
                                  f"Capa 0: la pieza queda a {max(gap, 0):.1f} mm del borde de la cama; los bordes "
                                  "suelen estar más fríos y despegar.",
                                  {"gap_mm": round(gap, 2), "margin_mm": t.bed_edge_margin_mm}))
    speed = resolve_value(config, "first_layer_speed", "perimeter_speed")
    if speed is not None and speed > t.first_layer_speed_mm_s:
        risks.append(Risk("first_layer_speed", "warning", "measured", (0, 0),
                          f"Capa 0: primera capa a {speed:g} mm/s (recomendado ≤ {t.first_layer_speed_mm_s:g}).",
                          {"speed_mm_s": speed, "threshold_mm_s": t.first_layer_speed_mm_s}))
    risks.sort(key=lambda r: (_RANK[r.severity], r.layers[0] if r.layers else -1))
    return risks
