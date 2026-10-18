import io
from pathlib import Path

import pytest
from conftest import MODELS
from profiles import MK4S

from prusaslicer_mcp.gcode.toolpaths import analyze_toolpaths
from prusaslicer_mcp.runner import run_cli

FIXTURES = Path(__file__).parent / "fixtures"


def test_toolpaths_mini():
    r = analyze_toolpaths(FIXTURES / "mini.gcode", filament_diameter=1.75)
    l0 = r.layers[0]
    assert l0.by_type["External perimeter"].length_mm == pytest.approx(40)
    assert r.travel.length_mm == pytest.approx(5)
    assert r.retractions == 1 and l0.retractions == 1
    assert l0.bbox == (0, 0, 10, 10)
    assert l0.contact_area_mm2 == pytest.approx(40 * 0.45)
    # the unretraction (pure E move) adds no path length
    assert r.by_type["External perimeter"].length_mm == pytest.approx(50)
    assert len(r.layers) == 2 and r.layers[1].z == pytest.approx(0.4)
    assert r.has_type_markers and r.confidence == "high"


def test_toolpaths_absolute_e():
    r = analyze_toolpaths(FIXTURES / "abs_e.gcode", filament_diameter=1.75)
    assert r.retractions == 1
    assert sum(t.length_mm for t in r.by_type.values()) == pytest.approx(10)
    assert r.travel.length_mm == pytest.approx(10)


def test_unsupported_lowers_confidence(tmp_path):
    p = tmp_path / "g10.gcode"
    p.write_text((FIXTURES / "mini.gcode").read_text() + "G10\nG11\n", encoding="utf-8")
    r = analyze_toolpaths(p, filament_diameter=1.75)
    assert r.unsupported.get("G10/G11") == 2 and r.confidence != "high"


def test_m73_layer_times():
    r = analyze_toolpaths(FIXTURES / "m73.gcode", filament_diameter=1.75)
    assert r.layers[0].time_s == pytest.approx(60) and r.layers[0].time_source == "m73"


def test_volumetric_and_axis_speed():
    r = analyze_toolpaths(FIXTURES / "mini.gcode", filament_diameter=1.75)
    l0 = r.layers[0]
    # 0.5 mm of 1.75 filament over 10 mm at 20 mm/s -> 0.5*2.405/0.5 s
    assert l0.max_volumetric_mm3s == pytest.approx(0.5 * 3.14159265 * 0.875**2 / 0.5, rel=1e-3)
    assert l0.max_vx_mm_s == pytest.approx(20) and l0.max_vy_mm_s == pytest.approx(100)


class _IterOnly:
    """Text file that can only be iterated line by line."""

    def __init__(self, f):
        self._f = f

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._f.close()

    def __iter__(self):
        return iter(self._f)

    def read(self, *a):
        raise AssertionError("must stream, not read()")

    def readlines(self, *a):
        raise AssertionError("must stream, not readlines()")


def test_toolpaths_streaming_does_not_readlines(monkeypatch):
    import prusaslicer_mcp.gcode.toolpaths as tp

    def fake_open(file, mode="r", *a, **k):
        f = io.open(file, mode, *a, **k)
        return f if "b" in mode else _IterOnly(f)

    monkeypatch.setattr(tp, "open", fake_open, raising=False)
    r = analyze_toolpaths(FIXTURES / "mini.gcode", filament_diameter=1.75)
    assert len(r.layers) == 2


@pytest.mark.slicer
def test_toolpaths_benchy_types(install, vendor_datadir, tmp_path):
    out = tmp_path / "benchy.gcode"
    run_cli(install, ["--datadir", vendor_datadir, "--printer-profile", MK4S[0], "--print-profile", MK4S[1],
                      "--material-profile", MK4S[2], "--no-binary-gcode", "--export-gcode", "-o", out,
                      MODELS / "3DBenchy.stl"])
    r = analyze_toolpaths(out)
    assert "Overhang perimeter" in r.by_type and "Bridge infill" in r.by_type
    assert r.has_type_markers and r.confidence == "high"
    assert r.time_scale > 0
