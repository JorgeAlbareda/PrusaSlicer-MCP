from pathlib import Path

import pytest

from prusaslicer_mcp.display import viewer_command
from prusaslicer_mcp.errors import PrusaMcpError, SlicerNotFoundError
from prusaslicer_mcp.install import SlicerInstall

D = Path("C:/PS")
FULL = SlicerInstall(console=D / "c.exe", gui=D / "gui.exe", gcodeviewer=D / "viewer.exe", resources=None, version="2.9.4")


@pytest.mark.parametrize("name", ["a.3mf", "a.stl", "a.obj", "a.step", "a.STL"])
def test_models_open_in_gui_single_instance(name):
    assert viewer_command(FULL, Path(name)) == [str(D / "gui.exe"), "--single-instance", str(Path(name))]


def test_gcode_opens_in_viewer():
    assert viewer_command(FULL, Path("x.gcode")) == [str(D / "viewer.exe"), str(Path("x.gcode"))]


def test_gcode_without_viewer_uses_gui_flag():
    inst = SlicerInstall(console=D / "c.exe", gui=D / "gui.exe", gcodeviewer=None, resources=None, version="2.9.4")
    assert viewer_command(inst, Path("x.gcode")) == [str(D / "gui.exe"), "--gcodeviewer", str(Path("x.gcode"))]


def test_unsupported_extension():
    with pytest.raises(PrusaMcpError):
        viewer_command(FULL, Path("x.txt"))


def test_no_gui():
    inst = SlicerInstall(console=D / "c.exe", gui=None, gcodeviewer=None, resources=None, version="2.9.4")
    with pytest.raises(SlicerNotFoundError):
        viewer_command(inst, Path("x.3mf"))
