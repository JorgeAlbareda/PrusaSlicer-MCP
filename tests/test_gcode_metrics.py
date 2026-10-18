from pathlib import Path

from prusaslicer_mcp.gcode.metrics import get_gcode_metrics, parse_duration, resolve_value

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_duration():
    assert parse_duration("41m 6s") == 2466
    assert parse_duration("14m 31s") == 871
    assert parse_duration("1d 2h 3m 4s") == 93784
    assert parse_duration("") is None


def test_metrics_kobra_tail():
    m = get_gcode_metrics(FIXTURES / "tail_kobra.gcode")
    assert m.print_time_s == 871
    assert m.filament_mm == 1295.01 and m.filament_g == 3.86
    assert m.printer == "Anycubic Kobra 2 MAX"
    assert m.filaments == ["Anycubic PLA @Kobra2MAX"]
    assert m.layer_height == 0.2 and m.first_layer_height == 0.24


def test_grams_none_when_density_zero(tmp_path):
    text = (FIXTURES / "tail_kobra.gcode").read_text(encoding="utf-8")
    text = text.replace("; filament_density = 1.24", "; filament_density = 0")
    p = tmp_path / "z.gcode"
    p.write_text(text, encoding="utf-8")
    assert get_gcode_metrics(p).filament_g is None


def test_resolve_value_percent():
    cfg = {"first_layer_speed": "50%", "perimeter_speed": "60", "infill_speed": "80"}
    assert resolve_value(cfg, "first_layer_speed", "perimeter_speed") == 30
    assert resolve_value(cfg, "infill_speed") == 80
    assert resolve_value(cfg, "first_layer_speed") is None
    assert resolve_value(cfg, "missing") is None
