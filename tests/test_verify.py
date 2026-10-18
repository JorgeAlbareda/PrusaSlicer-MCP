from pathlib import Path

import pytest

from prusaslicer_mcp.errors import BinaryGcodeError
from prusaslicer_mcp.verify import (
    CRITICAL_KEYS,
    build_expected,
    compare,
    expected_ids,
    normalize,
    read_effective_config,
    verify,
)

TAIL = Path(__file__).parent / "fixtures" / "tail_kobra.gcode"


def test_read_effective_config_fixture():
    cfg = read_effective_config(TAIL)
    assert cfg["bed_shape"] == "0x0,430x0,430x430,0x430"
    assert cfg["post_process"] == ""
    assert "filament used [mm]" not in cfg


def test_read_effective_config_large_file(tmp_path):
    big = tmp_path / "big.gcode"
    with big.open("w", encoding="utf-8") as f:
        f.write("G1 X1 Y1 E0.1\n" * 300_000)
        f.write(TAIL.read_text(encoding="utf-8"))
    assert read_effective_config(big)["printer_model"] == "KOBRA2MAX"


def test_binary_gcode_rejected(tmp_path):
    p = tmp_path / "b.gcode"
    p.write_bytes(b"GCDE\x01\x00\x00\x00rest")
    with pytest.raises(BinaryGcodeError):
        read_effective_config(p)


def test_verify_quoted_ids():
    effective = {"filament_settings_id": '"K2M PLA"', "print_settings_id": "0.20mm SPEED @MK4S 0.4"}
    expected = {"filament_settings_id": "K2M PLA", "print_settings_id": "0.20mm SPEED @MK4S 0.4"}
    assert compare(effective, expected) == []


def test_numeric_normalization():
    assert normalize("0.20") == normalize("0.2")
    assert normalize("15%") == normalize("15%")
    assert normalize("60") == normalize("60.0")
    assert compare({"layer_height": "0.20", "fill_density": "15%"}, {"layer_height": "0.2", "fill_density": "15%"}) == []


def test_mismatch_reported():
    (m,) = compare({"fill_density": "15%"}, {"fill_density": "40%"})
    assert (m.key, m.expected, m.actual) == ("fill_density", "40%", "15%")


def test_missing_key_reported():
    (m,) = compare({}, {"fill_density": "40%"})
    assert m.actual is None


def test_build_expected_overrides_win_and_unchecked_listed():
    ids = expected_ids("P", "Q", ["F"])
    source = {"layer_height": "0.2", "bed_shape": "0x0,1x0,1x1,0x1", "fill_density": "10%"}
    expected, unchecked = build_expected(ids, source, {"layer_height": "0.15"})
    assert expected["layer_height"] == "0.15"
    assert expected["bed_shape"] == "0x0,1x0,1x1,0x1"
    assert "fill_density" not in expected  # not critical, not overridden
    assert "nozzle_diameter" in unchecked
    assert expected["filament_settings_id"] == "F"


def test_build_expected_without_source_marks_all_unchecked():
    expected, unchecked = build_expected({}, None, {})
    assert set(unchecked) == set(CRITICAL_KEYS) and expected == {}


def test_verify_end_to_end_fixture():
    expected = {**expected_ids("Anycubic Kobra 2 MAX", "0.20mm Standard @Kobra2MAX", ["Anycubic PLA @Kobra2MAX"]),
                "bed_shape": "0x0,430x0,430x430,0x430"}
    v = verify(TAIL, expected, ["nozzle_diameter"])
    assert v.ok and "bed_shape" in v.checked_keys and v.unchecked_keys == ["nozzle_diameter"]
