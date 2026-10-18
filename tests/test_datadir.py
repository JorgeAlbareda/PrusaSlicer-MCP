from pathlib import Path

import pytest
from conftest import MODELS
from profiles import KOBRA, MK4S

from prusaslicer_mcp import datadir as dd
from prusaslicer_mcp.errors import PrusaMcpError
from prusaslicer_mcp.preset_keys import classify_key
from prusaslicer_mcp.runner import run_cli

FIXTURES = Path(__file__).parent / "fixtures"


def test_default_datadir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(dd.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert dd.default_datadir() == tmp_path / "PrusaSlicer"


@pytest.mark.slicer
def test_list_printers_vendor(install, vendor_datadir):
    printers = {p.name: p for p in dd.list_printers(install, vendor_datadir)}
    p = printers["Original Prusa MK4S 0.4 nozzle"]
    assert p.bed_width == 250 and p.vendor == "Prusa Research" and not p.user


@pytest.mark.slicer
def test_list_printers_user_kobra(install, kobra_datadir):
    (p,) = dd.list_printers(install, kobra_datadir)
    assert p.name == KOBRA[0] and p.user and p.bed_width == 430 and p.extruders == 1


@pytest.mark.slicer
def test_compatible_profiles_mk4s(install, vendor_datadir):
    profiles = {p.name: p for p in dd.list_compatible_profiles(install, vendor_datadir, MK4S[0])}
    assert "Prusament PLA @MK4S" in profiles[MK4S[1]].filaments


def test_save_user_preset_refuses_overwrite(tmp_path):
    dd.save_user_preset(tmp_path, "print", "Mio", {"fill_density": "20%"})
    with pytest.raises(PrusaMcpError):
        dd.save_user_preset(tmp_path, "print", "Mio", {"fill_density": "30%"})


def test_save_user_preset_backup_on_overwrite(tmp_path):
    p = dd.save_user_preset(tmp_path, "print", "Mio", {"fill_density": "20%"})
    dd.save_user_preset(tmp_path, "print", "Mio", {"fill_density": "30%"}, overwrite=True)
    backups = list((tmp_path / "print").glob("Mio.ini.bak-*"))
    assert len(backups) == 1 and "20%" in backups[0].read_text(encoding="utf-8")
    assert "30%" in p.read_text(encoding="utf-8")


def test_save_user_preset_rejects_bad_name(tmp_path):
    with pytest.raises(PrusaMcpError):
        dd.save_user_preset(tmp_path, "print", "a/b", {})


def test_import_bundle_kobra_fixture(tmp_path):
    paths, warnings = dd.import_bundle(tmp_path, (FIXTURES / "kobra2max_bundle.ini").read_text(encoding="utf-8"))
    assert len(paths) == 3
    printer = (tmp_path / "printer" / "Anycubic Kobra 2 MAX.ini").read_text(encoding="utf-8")
    assert "Hostname" not in printer
    assert any("Hostname" in w for w in warnings)


BUNDLE_INHERITS = """
[printer:Base]
bed_shape = 0x0,200x0,200x200,0x200
start_gcode = G28
max_print_height = 180

[printer:Child]
inherits = Base
nozzle_diameter = 0.6
"""


def test_import_bundle_resolves_inherits(tmp_path):
    dd.import_bundle(tmp_path, BUNDLE_INHERITS)
    child = (tmp_path / "printer" / "Child.ini").read_text(encoding="utf-8")
    assert "bed_shape = 0x0,200x0,200x200,0x200" in child
    assert "start_gcode = G28" in child and "nozzle_diameter = 0.6" in child
    assert "inherits" not in child


def test_import_bundle_inherits_cycle_errors(tmp_path):
    cyc = "[print:A]\ninherits = B\n\n[print:B]\ninherits = A\n"
    with pytest.raises(PrusaMcpError):
        dd.import_bundle(tmp_path, cyc)


def test_import_bundle_strips_post_process(tmp_path):
    _, warnings = dd.import_bundle(tmp_path, "[print:P]\npost_process = evil.exe\nfill_density = 10%\n")
    assert "post_process" not in (tmp_path / "print" / "P.ini").read_text(encoding="utf-8")
    assert any("post_process" in w for w in warnings)


def test_classify_key():
    assert classify_key("fill_density") == "print"
    assert classify_key("temperature") == "filament"
    assert classify_key("bed_shape") == "printer"
    assert classify_key("machine_max_feedrate_x") == "printer"
    assert classify_key("nozzle_diameter") == "printer"
    assert classify_key("foo") is None


@pytest.mark.slicer
def test_resolve_system_preset_values(install, vendor_datadir):
    values = dd.resolve_preset_values(install, vendor_datadir, "printer", MK4S[0])
    assert values["nozzle_diameter"] == "0.4"
    assert values["printer_model"] == "MK4S"


def test_resolve_user_preset_values(kobra_datadir):
    values = dd.resolve_preset_values(None, kobra_datadir, "printer", KOBRA[0])
    assert values["bed_shape"] == "0x0,430x0,430x430,0x430"


def test_resolve_unknown_preset_is_none(kobra_datadir):
    assert dd.resolve_preset_values(None, kobra_datadir, "print", "nope") is None


@pytest.mark.slicer
def test_example_kobra_profiles_load_cleanly(install, kobra_datadir, tmp_path):
    out = tmp_path / "k.gcode"
    res = run_cli(
        install,
        ["--datadir", kobra_datadir, "--printer-profile", KOBRA[0], "--print-profile", KOBRA[1],
         "--material-profile", KOBRA[2], "--no-binary-gcode", "--export-gcode", "-o", out,
         MODELS / "20mm_cube.obj"],
    )
    assert out.exists()
    assert not [w for w in res.warnings if "incorrect keys" in w]
    assert res.errors == []


def test_resolve_user_preset_ignores_inherits(tmp_path):
    # PrusaSlicer loads a user preset as defaults + its own keys; `inherits` is metadata only.
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "V.ini").write_text("[print:Base]\nlayer_height = 0.3\nperimeters = 4\n", encoding="utf-8")
    (tmp_path / "print").mkdir()
    (tmp_path / "print" / "Mine.ini").write_text("inherits = Base\nfill_density = 25%\n", encoding="utf-8")
    assert dd.resolve_preset_values(None, tmp_path, "print", "Mine") == {"fill_density": "25%"}


def test_import_bundle_flattens_from_installed_system_parent(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "V.ini").write_text("[print:Base]\nlayer_height = 0.3\nperimeters = 4\n", encoding="utf-8")
    dd.import_bundle(tmp_path, "[print:Child]\ninherits = Base\nfill_density = 25%\n")
    child = (tmp_path / "print" / "Child.ini").read_text(encoding="utf-8")
    assert "layer_height = 0.3" in child and "perimeters = 4" in child and "fill_density = 25%" in child


def test_import_bundle_missing_parent_warns_defaults(tmp_path):
    _, warnings = dd.import_bundle(tmp_path, "[print:Child]\ninherits = Nope\nfill_density = 25%\n")
    assert any("valores por defecto" in w for w in warnings)
