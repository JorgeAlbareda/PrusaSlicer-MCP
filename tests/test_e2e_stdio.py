import json
import os
import sys

import pytest
from conftest import MODELS
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from profiles import MK4S

pytestmark = pytest.mark.slicer


def data(result):
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def test_e2e_stdio(install, vendor_datadir, tmp_path):
    env = {
        "PRUSASLICER_DATADIR": str(vendor_datadir),
        "PRUSASLICER_PATH": str(install.console.parent),
        "PRUSASLICER_MCP_WORKDIR": str(tmp_path / "work"),
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "prusaslicer_mcp"], env={**os.environ, **env})
    async with Client(params) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert "slice" in names
        data(await c.call_tool("select_profiles", {"printer": MK4S[0], "print_profile": MK4S[1], "filaments": [MK4S[2]]}))
        data(await c.call_tool("add_model", {"path": str(MODELS / "20mm_cube.obj"), "copies": 2}))
        placed = data(await c.call_tool("arrange_plate", {}))["placements"]
        assert len(placed) == 2
        sliced = data(await c.call_tool("slice", {}))
        assert sliced["verification"]["ok"] is True and len(sliced["placements"]) == 2
        risks = data(await c.call_tool("find_print_risks", {"gcode_path": sliced["gcode_path"]}))
        assert isinstance(risks["risks"], list)
