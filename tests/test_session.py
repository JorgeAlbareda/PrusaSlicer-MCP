import pytest
from conftest import MODELS

from prusaslicer_mcp.errors import PrusaMcpError
from prusaslicer_mcp.session import Session

CUBE = MODELS / "20mm_cube.obj"


def test_ids_not_reused():
    s = Session()
    a = s.add_object(CUBE)
    b = s.add_object(CUBE)
    s.remove_object(b.id)
    c = s.add_object(CUBE)
    assert (a.id, b.id, c.id) == (1, 2, 3)


def test_unsupported_extension(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("x")
    with pytest.raises(PrusaMcpError):
        Session().add_object(f)


def test_missing_file(tmp_path):
    with pytest.raises(PrusaMcpError):
        Session().add_object(tmp_path / "nope.stl")


def test_unknown_id():
    with pytest.raises(PrusaMcpError):
        Session().remove_object(7)


def test_transform_absolute():
    s = Session()
    o = s.add_object(CUBE)
    s.transform(o.id, rotate_z=45)
    s.transform(o.id, rotate_z=30)
    assert o.rotate_z == 30


def test_invalid_scale_and_copies():
    s = Session()
    o = s.add_object(CUBE)
    with pytest.raises(PrusaMcpError):
        s.transform(o.id, scale_percent=0)
    with pytest.raises(PrusaMcpError):
        s.transform(o.id, copies=0)


def test_copies_create_instances():
    s = Session()
    o = s.add_object(CUBE, copies=3)
    assert len(o.instances) == 3
    s.transform(o.id, copies=1)
    assert len(o.instances) == 1


def test_rotation_change_clears_unfixed_positions_only():
    s = Session()
    o = s.add_object(CUBE, copies=2)
    s.place(o.id, 0, 100, 100)
    o.instances[1].center = (50, 50)  # as if set by arrange
    s.transform(o.id, rotate_z=10)
    assert o.instances[0].center == (100, 100) and o.instances[0].fixed
    assert o.instances[1].center is None


def test_unplace_all():
    s = Session()
    o = s.add_object(CUBE, copies=2)
    s.place(o.id, 0, 10, 10)
    o.instances[1].center = (1, 1)
    s.unplace_all()
    assert o.instances[0].center == (10, 10) and o.instances[1].center is None
    s.unplace_all(include_fixed=True)
    assert o.instances[0].center is None and not o.instances[0].fixed


def test_place_bad_instance():
    s = Session()
    o = s.add_object(CUBE)
    with pytest.raises(PrusaMcpError):
        s.place(o.id, 5, 1, 1)


def test_snapshot_independent():
    s = Session()
    o = s.add_object(CUBE)
    s.set_setting("fill_density", "20%")
    snap = s.snapshot()
    s.transform(o.id, rotate_z=90)
    s.set_setting("fill_density", "30%")
    assert snap.objects[0].rotate_z == 0 and snap.overrides["fill_density"] == "20%"


def test_settings_and_profiles():
    s = Session()
    s.select_profiles("P", "Q", ["F"])
    s.set_setting("layer_height", "0.15")
    s.reset_setting("layer_height")
    d = s.to_dict()
    assert d["printer"] == "P" and d["filaments"] == ["F"] and d["overrides"] == {}


def test_set_setting_escapes_real_newlines():
    # Final review I4: a raw newline would break the overrides .ini.
    s = Session()
    s.set_setting("start_gcode", "G28\nG1 Z5\r\n")
    assert s.overrides["start_gcode"] == r"G28\nG1 Z5\n"


@pytest.mark.parametrize("key", ["post_process ", "a=b", "fill density", "", "x\ny"])
def test_set_setting_rejects_bad_keys(key):
    with pytest.raises(PrusaMcpError):
        Session().set_setting(key, "1")
