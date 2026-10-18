import pytest
from conftest import MODELS
from profiles import KOBRA

from prusaslicer_mcp.cli_engine import CliEngine
from prusaslicer_mcp.gcode.metrics import get_gcode_metrics
from prusaslicer_mcp.gcode.risks import RiskThresholds, find_print_risks
from prusaslicer_mcp.gcode.toolpaths import LayerStats, ToolpathReport, TypeStats, analyze_toolpaths

BASE_CONFIG = {
    "bed_shape": "0x0,250x0,250x210,0x210",
    "filament_type": "PLA",
    "brim_width": "0",
    "slowdown_below_layer_time": "8",
    "perimeter_speed": "60",
    "first_layer_speed": "20",
    "machine_limits_usage": "time_estimate_only",
    "machine_max_feedrate_x": "200",
    "machine_max_feedrate_y": "200",
    "machine_max_acceleration_extruding": "4000",
    "filament_max_volumetric_speed": "0",
    "max_volumetric_speed": "0",
}


def layer(i, **kw):
    defaults = dict(index=i, z=0.2 * (i + 1), height=0.2, time_s=30.0, time_source="estimate",
                    by_type={"Perimeter": TypeStats(length_mm=100)}, bbox=(100, 100, 120, 120) if i == 0 else None,
                    contact_area_mm2=200.0 if i == 0 else 0)
    defaults.update(kw)
    return LayerStats(**defaults)


def report(layers):
    return ToolpathReport(by_type={}, layers=layers, travel=TypeStats(), retractions=0, time_scale=1.0,
                          has_type_markers=True, unsupported={}, confidence="high")


def kinds(risks):
    return {r.kind for r in risks}


def test_no_risks_clean_report():
    assert find_print_risks(report([layer(0), layer(1)]), BASE_CONFIG) == []


def test_short_layer_time_estimate_is_info():
    (r,) = find_print_risks(report([layer(0), layer(1, time_s=3.0)]), BASE_CONFIG)
    assert r.kind == "short_layer_time" and r.severity == "info" and r.basis == "heuristic"
    assert r.evidence["threshold_s"] == 8 and "aproximad" in r.message


def test_short_layer_time_m73_is_warning():
    (r,) = find_print_risks(report([layer(0), layer(1, time_s=3.0, time_source="m73")]), BASE_CONFIG)
    assert r.severity == "warning"


def test_grouping_consecutive_layers():
    layers = [layer(0)] + [layer(i, time_s=2.0) for i in range(1, 6)] + [layer(6)]
    (r,) = find_print_risks(report(layers), BASE_CONFIG)
    assert r.layers == (1, 5)


def test_warping_high_for_abs_large_contact():
    cfg = {**BASE_CONFIG, "filament_type": "ABS"}
    risks = find_print_risks(report([layer(0, contact_area_mm2=12000.0)]), cfg)
    (r,) = [r for r in risks if r.kind == "warping_risk"]
    assert r.severity == "high" and r.evidence["threshold_cm2"] == 100


def test_scattered_small_objects_no_warping():
    cfg = {**BASE_CONFIG, "filament_type": "ABS"}
    risks = find_print_risks(report([layer(0, bbox=(10, 10, 240, 200), contact_area_mm2=800.0)]), cfg)
    assert not [r for r in risks if r.kind == "warping_risk" and r.severity == "high"]


def test_warping_near_bed_edge():
    risks = find_print_risks(report([layer(0, bbox=(2, 100, 30, 120))]), BASE_CONFIG)
    (r,) = [r for r in risks if r.kind == "warping_risk"]
    assert r.severity == "warning" and r.evidence["margin_mm"] == 5


def test_overhangs():
    bt = {"Perimeter": TypeStats(length_mm=50), "External perimeter": TypeStats(length_mm=20),
          "Overhang perimeter": TypeStats(length_mm=30)}
    (r,) = find_print_risks(report([layer(0), layer(1, by_type=bt)]), BASE_CONFIG)
    assert r.kind == "overhangs" and r.evidence["fraction"] == pytest.approx(0.3)


def test_long_bridge():
    (r,) = find_print_risks(report([layer(0), layer(1, max_bridge_move_mm=40.0)]), BASE_CONFIG)
    assert r.kind == "long_bridge" and r.basis == "measured" and r.evidence["threshold_mm"] == 25


def test_volumetric_uses_stricter_limit():
    cfg = {**BASE_CONFIG, "filament_max_volumetric_speed": "15", "max_volumetric_speed": "12"}
    (r,) = find_print_risks(report([layer(0, max_volumetric_mm3s=13.0)]), cfg)
    assert r.kind == "volumetric_flow" and r.severity == "high" and r.evidence["limit_mm3s"] == 12


def test_volumetric_skipped_without_limits():
    assert find_print_risks(report([layer(0, max_volumetric_mm3s=50.0)]), BASE_CONFIG) == []


def test_machine_limits_per_axis_and_peak_accel():
    (r,) = find_print_risks(report([layer(0, max_vx_mm_s=250.0, max_accel=5000.0)]), BASE_CONFIG)
    assert r.kind == "machine_limits"
    assert r.evidence["max_vx_mm_s"] == 250 and r.evidence["max_accel"] == 5000


def test_machine_limits_ignored_when_usage_ignore():
    cfg = {**BASE_CONFIG, "machine_limits_usage": "ignore"}
    assert find_print_risks(report([layer(0, max_vx_mm_s=250.0)]), cfg) == []


def test_retractions():
    (r,) = find_print_risks(report([layer(0), layer(1, retractions=80)]), BASE_CONFIG)
    assert r.kind == "retractions" and r.severity == "info"


def test_first_layer_speed_percent_resolved():
    cfg = {**BASE_CONFIG, "first_layer_speed": "150%", "perimeter_speed": "60"}
    (r,) = find_print_risks(report([layer(0)]), cfg)
    assert r.kind == "first_layer_speed" and r.evidence["speed_mm_s"] == 90


def test_custom_thresholds():
    t = RiskThresholds(bridge_move_mm=50.0)
    assert find_print_risks(report([layer(0), layer(1, max_bridge_move_mm=40.0)]), BASE_CONFIG, t) == []


@pytest.mark.slicer
def test_bridge_model_flags_bridge(install, kobra_datadir, tmp_path):
    e = CliEngine(install, kobra_datadir, tmp_path / "w")
    e.select_profiles(*KOBRA[:2], [KOBRA[2]])
    e.add_model(MODELS / "bridge.obj")
    g = e.slice().gcode_path
    risks = find_print_risks(analyze_toolpaths(g), get_gcode_metrics(g).config)
    assert kinds(risks) & {"long_bridge", "overhangs"}
