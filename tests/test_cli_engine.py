import shutil
import sys
from pathlib import Path

import pytest
from conftest import MODELS
from profiles import KOBRA, MK4S

from prusaslicer_mcp import cli_engine as ce
from prusaslicer_mcp.cli_engine import CliEngine
from prusaslicer_mcp.errors import (
    BundleIniError,
    CliError,
    EngineCapabilityError,
    PrusaMcpError,
    VerificationError,
)
from prusaslicer_mcp.gcode.toolpaths import analyze_toolpaths
from prusaslicer_mcp.placement import parse_bed_shape, validate
from prusaslicer_mcp.verify import read_effective_config

pytestmark = pytest.mark.slicer

CUBE = MODELS / "20mm_cube.obj"


@pytest.fixture
def kobra(install, kobra_datadir, tmp_path):
    e = CliEngine(install, kobra_datadir, tmp_path / "work")
    e.select_profiles(*KOBRA[:2], [KOBRA[2]])
    return e


@pytest.fixture
def mk4s(install, vendor_datadir, tmp_path):
    e = CliEngine(install, vendor_datadir, tmp_path / "work")
    e.select_profiles(*MK4S[:2], [MK4S[2]])
    return e


def test_slice_mk4s_cube_verified(mk4s):
    mk4s.add_model(CUBE)
    r = mk4s.slice()
    assert r.verification.ok and "nozzle_diameter" in r.verification.checked_keys
    assert read_effective_config(r.gcode_path)["printer_model"] == "MK4S"
    assert r.gcode_path.read_bytes()[:4] != b"GCDE"
    assert r.metrics.print_time_s and r.metrics.print_time_s > 0


def test_slice_kobra_benchy(kobra):
    kobra.add_model(MODELS / "3DBenchy.stl")
    r = kobra.slice()
    assert read_effective_config(r.gcode_path)["bed_shape"] == "0x0,430x0,430x430,0x430"


def test_override_changes_result(kobra, tmp_path):
    kobra.add_model(CUBE)
    kobra.set_setting("fill_density", "15%")
    low = kobra.slice(tmp_path / "low.gcode").metrics.filament_mm
    kobra.set_setting("fill_density", "40%")
    r = kobra.slice(tmp_path / "high.gcode")
    assert r.metrics.filament_mm > low
    assert "fill_density" in r.verification.checked_keys


def test_two_objects_positions_resolved(kobra):
    kobra.add_model(CUBE)
    kobra.add_model(MODELS / "cylinder.stl", copies=2)
    r = kobra.slice()
    assert len(r.placements) == 3
    assert validate(r.placements, parse_bed_shape("0x0,430x0,430x430,0x430"), 6) == []
    bbox = analyze_toolpaths(r.gcode_path).layers[0].bbox
    for f in r.placements:
        cx, cy = f.center
        assert bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def test_arrange_plate_returns_positions(kobra):
    kobra.add_model(CUBE, copies=3)
    placed = kobra.arrange_plate()
    assert len(placed) == 3 and all(f.center for f in placed)
    assert all(i["center"] for o in kobra.get_plate()["objects"] for i in o["instances"])


def test_fixed_position_kept(kobra):
    kobra.add_model(CUBE)
    kobra.place_instance(1, 0, 300, 300)
    r = kobra.slice()
    assert r.placements[0].center == (300, 300)
    bbox = analyze_toolpaths(r.gcode_path).layers[0].bbox
    # the first layer includes the brim, so compare the bbox centre
    assert (bbox[0] + bbox[2]) / 2 == pytest.approx(300, abs=0.5)
    assert (bbox[1] + bbox[3]) / 2 == pytest.approx(300, abs=0.5)


def test_overlap_rejected(kobra):
    kobra.add_model(CUBE, copies=2)
    kobra.place_instance(1, 0, 100, 100)
    kobra.place_instance(1, 1, 100, 100)
    with pytest.raises(PrusaMcpError) as e:
        kobra.slice()
    assert "solapa" in e.value.message


def _engine_with_post_process(install, datadir, tmp_path, allow):
    marker = tmp_path / "marker.txt"
    script = tmp_path / "pp.bat"
    script.write_text(f"@echo ran> {marker}\r\n", encoding="utf-8")
    preset = datadir / "print" / f"{KOBRA[1]}.ini"
    preset.write_text(preset.read_text(encoding="utf-8") + f"post_process = {script.as_posix()}\n", encoding="utf-8")
    e = CliEngine(install, datadir, tmp_path / "work", allow_post_process=allow)
    e.select_profiles(*KOBRA[:2], [KOBRA[2]])
    e.add_model(CUBE)
    return e, marker


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .bat post-process script")
def test_post_process_runs_when_allowed(install, kobra_datadir, tmp_path):
    e, marker = _engine_with_post_process(install, kobra_datadir, tmp_path, allow=True)
    e.slice()
    assert marker.exists()  # positive control: the script really is executable


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .bat post-process script")
def test_post_process_not_executed(install, kobra_datadir, tmp_path):
    e, marker = _engine_with_post_process(install, kobra_datadir, tmp_path, allow=False)
    r = e.slice()
    assert not marker.exists()
    assert read_effective_config(r.gcode_path)["post_process"] == ""
    with pytest.raises(PrusaMcpError):
        e.set_setting("post_process", "evil.exe")


def test_bundle_config_file_rejected(kobra):
    with pytest.raises(BundleIniError):
        kobra.use_config_file(MODELS.parent / "fixtures" / "kobra2max_bundle.ini")


def test_missing_profile_errors(kobra):
    kobra.select_profiles(KOBRA[0], "no existe", [KOBRA[2]])
    kobra.add_model(CUBE)
    with pytest.raises(CliError) as e:
        kobra.slice()
    assert "wasn't found" in e.value.message


def test_slice_without_profiles_or_objects_errors(install, kobra_datadir, tmp_path):
    e = CliEngine(install, kobra_datadir, tmp_path / "w")
    with pytest.raises(PrusaMcpError):
        e.slice()
    e.select_profiles(*KOBRA[:2], [KOBRA[2]])
    with pytest.raises(PrusaMcpError):
        e.slice()


def test_slice_model_too_big_errors(mk4s):
    mk4s.add_model(MODELS / "3DBenchy.stl")
    mk4s.transform_object(1, scale_percent=1000)
    with pytest.raises(PrusaMcpError) as e:
        mk4s.slice()
    assert e.value.message


def test_slice_path_with_spaces_and_unicode(kobra, tmp_path):
    d = tmp_path / "Carpeta con espacios"
    d.mkdir()
    model = d / "pieza ñ.obj"
    shutil.copy(CUBE, model)
    kobra.add_model(model)
    r = kobra.slice(d / "salida ñ.gcode")
    assert r.gcode_path == d / "salida ñ.gcode" and r.gcode_path.exists()


def test_failed_verification_does_not_publish(kobra, tmp_path, monkeypatch):
    real = ce.build_expected

    def impossible(ids, source, overrides):
        expected, unchecked = real(ids, source, overrides)
        return {**expected, "layer_height": "9.99"}, unchecked

    monkeypatch.setattr(ce, "build_expected", impossible)
    kobra.add_model(CUBE)
    out = tmp_path / "never.gcode"
    with pytest.raises(VerificationError) as e:
        kobra.slice(out)
    assert not out.exists()
    assert e.value.verification.mismatches[0].key == "layer_height"


def test_get_setting_override_then_effective(kobra):
    assert kobra.get_setting("fill_density") is None
    kobra.set_setting("fill_density", "33%")
    assert kobra.get_setting("fill_density") == "33%"
    kobra.reset_setting("fill_density")
    kobra.add_model(CUBE)
    kobra.slice()
    assert kobra.get_setting("fill_density") == "15%"


def test_export_3mf(kobra, tmp_path):
    kobra.add_model(CUBE, copies=2)
    out = kobra.export_3mf(tmp_path / "plate.3mf")
    assert out.exists() and out.stat().st_size > 0


def test_save_profile_as_splits_by_kind(kobra, kobra_datadir):
    kobra.set_setting("fill_density", "25%")
    kobra.set_setting("temperature", "210")
    paths = kobra.save_profile_as("Mio")
    names = sorted(p.parent.name for p in paths)
    assert names == ["filament", "print"]
    text = (kobra_datadir / "print" / "Mio.ini").read_text(encoding="utf-8")
    # flattened: every print key of the parent, with the change applied (inherits is only metadata)
    assert "fill_density = 25%" in text and "perimeter_speed = 230" in text
    assert "\ntemperature = " not in text  # filament keys go to the filament preset


def test_save_profile_as_rejects_unknown_key(kobra):
    kobra.set_setting("no_such_key", "1")
    with pytest.raises(PrusaMcpError):
        kobra.save_profile_as("Mio")


def test_v2_only_methods_raise(kobra):
    with pytest.raises(EngineCapabilityError):
        kobra.set_variable_layer_height(1, 0.5)
    with pytest.raises(EngineCapabilityError):
        kobra.add_height_range_modifier(1, 0, 5, {})
    with pytest.raises(EngineCapabilityError):
        kobra.preview_layer(3)


def test_model_info_cube(kobra):
    info = kobra.add_model(CUBE)["model_info"]
    assert float(info["size_x"]) == pytest.approx(20)


def test_saved_profile_keeps_unchanged_parent_values(kobra):
    # Final review C1: a sparse preset loads as PrusaSlicer defaults + changes.
    kobra.set_setting("fill_density", "25%")
    kobra.save_profile_as("Mio")
    kobra.reset_setting("fill_density")
    kobra.select_profiles(KOBRA[0], "Mio", [KOBRA[2]])
    kobra.add_model(CUBE)
    cfg = read_effective_config(kobra.slice().gcode_path)
    assert cfg["fill_density"] == "25%"
    assert cfg["layer_height"] == "0.2" and cfg["first_layer_height"] == "0.24"
    assert cfg["perimeter_speed"] == "230"


def test_save_profile_as_rejects_system_preset_name(mk4s):
    mk4s.set_setting("fill_density", "25%")
    with pytest.raises(PrusaMcpError) as e:
        mk4s.save_profile_as(MK4S[1])
    assert "sistema" in e.value.message


def test_object_outside_round_bed_rejected(kobra):
    # Final review I1: PrusaSlicer silently drops instances outside a non-rectangular bed.
    circle = ",".join(f"{100 * __import__('math').cos(a / 18 * 3.14159265):.3f}x"
                      f"{100 * __import__('math').sin(a / 18 * 3.14159265):.3f}" for a in range(36))
    kobra.set_setting("bed_shape", circle)
    kobra.add_model(CUBE, copies=2)
    kobra.place_instance(1, 0, 0, 0)
    kobra.place_instance(1, 1, -85, -85)
    with pytest.raises(PrusaMcpError) as e:
        kobra.slice()
    assert "fuera" in e.value.message


def test_publish_across_directories(tmp_path):
    src = tmp_path / "a" / "x.gcode"
    src.parent.mkdir()
    src.write_text("G28\n")
    dst = tmp_path / "b" / "y.gcode"
    ce.publish_file(src, dst)
    assert dst.read_text() == "G28\n" and not src.exists()


def test_publish_oserror_is_clear(tmp_path, monkeypatch):
    src = tmp_path / "x.gcode"
    src.write_text("G28\n")
    monkeypatch.setattr(ce.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left")))
    with pytest.raises(PrusaMcpError) as e:
        ce.publish_file(src, tmp_path / "out" / "y.gcode")
    assert "No se pudo guardar" in e.value.message and src.exists()
