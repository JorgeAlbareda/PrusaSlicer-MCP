from pathlib import Path

import pytest

from prusaslicer_mcp.errors import BundleIniError
from prusaslicer_mcp.ini import dump_flat, is_bundle, load_flat_file, parse_bundle, parse_flat

FIXTURES = Path(__file__).parent / "fixtures"
KOBRA_BUNDLE = FIXTURES / "kobra2max_bundle.ini"


def test_parse_flat_ignores_comments_and_blank():
    text = "# comment\n\nlayer_height = 0.2\n; also comment\nfill_density = 15%\n"
    assert parse_flat(text) == {"layer_height": "0.2", "fill_density": "15%"}


def test_values_keep_inner_spaces_and_escaped_newlines():
    text = "start_gcode = G90 ; abs\\nM83 ; rel\nend_filament_gcode = \n"
    values = parse_flat(text)
    assert values["start_gcode"] == "G90 ; abs\\nM83 ; rel"
    assert values["end_filament_gcode"] == ""


def test_is_bundle_true_for_kobra_fixture():
    assert is_bundle(KOBRA_BUNDLE.read_text(encoding="utf-8"))
    assert not is_bundle("layer_height = 0.2\n")


def test_parse_bundle_kobra():
    b = parse_bundle(KOBRA_BUNDLE.read_text(encoding="utf-8"))
    assert b["print"]["0.20mm Standard @Kobra2MAX"]["layer_height"] == "0.2"
    assert b["printer"]["Anycubic Kobra 2 MAX"]["bed_shape"] == "0x0,430x0,430x430,0x430"
    assert b["filament"]["Anycubic PLA @Kobra2MAX"]["temperature"] == "215"
    assert b["presets"][""]["printer"] == "Anycubic Kobra 2 MAX"


def test_load_flat_file_rejects_bundle():
    with pytest.raises(BundleIniError) as e:
        load_flat_file(KOBRA_BUNDLE)
    assert "import_profile_bundle" in e.value.message


def test_roundtrip_dump_parse():
    values = {"a": "1", "start_gcode": "G28\\nG1 Z5", "empty": ""}
    assert parse_flat(dump_flat(values)) == values
