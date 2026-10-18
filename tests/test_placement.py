import pytest

from prusaslicer_mcp.errors import PrusaMcpError
from prusaslicer_mcp.placement import Footprint, pack, parse_bed_shape, validate

BED = (0.0, 0.0, 250.0, 210.0)


def fp(oid, w, d, center=None, fixed=False, inst=0):
    return Footprint(object_id=oid, instance=inst, width=w, depth=d, center=center, fixed=fixed)


def test_parse_bed_shape():
    assert parse_bed_shape("0x0,430x0,430x430,0x430") == (0, 0, 430, 430)
    assert parse_bed_shape("-5x-5,245x-5,245x205,-5x205") == (-5, -5, 245, 205)


def test_pack_two_cubes_no_overlap():
    placed = pack([fp(1, 20, 20), fp(2, 20, 20)], BED, spacing=6)
    assert all(f.center for f in placed)
    assert validate(placed, BED, 6) == []


def test_pack_respects_fixed():
    fixed = fp(1, 50, 50, center=(30, 30), fixed=True)
    placed = pack([fixed, fp(2, 40, 40), fp(3, 40, 40)], BED, spacing=6)
    assert placed[0].center == (30, 30)
    assert validate(placed, BED, 6) == []


def test_pack_too_many_errors():
    with pytest.raises(PrusaMcpError):
        pack([fp(i, 100, 100) for i in range(30)], BED, spacing=6)


def test_pack_object_bigger_than_bed_errors():
    with pytest.raises(PrusaMcpError):
        pack([fp(1, 300, 20)], BED)


def test_validate_detects_overlap_and_out_of_bed():
    problems = validate([fp(1, 20, 20, (50, 50)), fp(2, 20, 20, (55, 55))], BED, 6)
    assert any("solapa" in p for p in problems)
    problems = validate([fp(1, 20, 20, (245, 100))], BED, 6)
    assert any("fuera" in p for p in problems)


def test_pack_centers_group_when_nothing_fixed():
    placed = pack([fp(1, 20, 20), fp(2, 20, 20)], BED, spacing=6)
    xs = [f.center[0] for f in placed]
    ys = [f.center[1] for f in placed]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(125)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(105)


def _circle(r=100, n=36):
    import math
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def test_validate_polygon_bed():
    poly = _circle()
    bed = (-100, -100, 100, 100)
    assert validate([fp(1, 20, 20, (0, 0))], bed, 6, polygon=poly) == []
    assert any("fuera" in p for p in validate([fp(1, 20, 20, (-85, -85))], bed, 6, polygon=poly))


def test_pack_stays_inside_polygon_bed():
    poly = _circle()
    placed = pack([fp(i, 20, 20) for i in range(6)], (-100, -100, 100, 100), 6, polygon=poly)
    assert validate(placed, (-100, -100, 100, 100), 6, polygon=poly) == []
