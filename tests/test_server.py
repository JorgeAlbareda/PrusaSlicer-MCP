import json
from pathlib import Path

import httpx
import mcp_types as types
import pytest
from mcp import Client

from prusaslicer_mcp.datadir import PrinterInfo, PrintProfileInfo
from prusaslicer_mcp.engine import SliceResult
from prusaslicer_mcp.errors import EngineCapabilityError
from prusaslicer_mcp.gcode.metrics import GcodeMetrics
from prusaslicer_mcp.placement import Footprint
from prusaslicer_mcp.server import build_server
from prusaslicer_mcp.verify import Verification

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED_TOOLS = {
    "get_slicer_info", "list_printers", "list_compatible_profiles", "select_profiles", "use_config_file",
    "get_setting", "set_setting", "reset_setting", "save_profile_as", "import_profile_bundle",
    "add_model", "get_plate", "remove_object", "clear_plate", "transform_object", "place_instance",
    "arrange_plate", "slice", "export_3mf", "get_gcode_metrics", "analyze_toolpaths", "find_print_risks",
    "show_in_slicer", "set_variable_layer_height", "add_height_range_modifier", "preview_layer",
    "list_print_hosts", "upload_gcode", "get_printer_status", "start_print", "pause_print", "resume_print",
    "cancel_print",
}


class FakeEngine:
    name = "fake"

    def __init__(self):
        self.calls: list[tuple] = []

    def _rec(self, *call):
        self.calls.append(call)

    def info(self):
        return {"engine": "fake", "version": "2.9.4", "supported_version": True}

    def list_printers(self):
        return [PrinterInfo("P", "V", "M", 1, 250, 210, 220, False)]

    def list_compatible_profiles(self, printer):
        return [PrintProfileInfo("Q", False, ["F"])]

    def get_plate(self):
        return {"objects": []}

    def get_setting(self, key):
        return None

    def select_profiles(self, printer, print_profile, filaments):
        self._rec("select_profiles", printer, print_profile, tuple(filaments))
        return []

    def use_config_file(self, path):
        self._rec("use_config_file", str(path))

    def set_setting(self, key, value):
        self._rec("set_setting", key, value)

    def reset_setting(self, key):
        self._rec("reset_setting", key)

    def add_model(self, path, copies=1):
        self._rec("add_model", str(path), copies)
        return {"object": {"id": 1}, "model_info": {"size_x": "20"}}

    def remove_object(self, object_id):
        self._rec("remove_object", object_id)

    def clear_plate(self):
        self._rec("clear_plate")

    def transform_object(self, object_id, **kw):
        self._rec("transform_object", object_id, tuple(sorted(kw.items())))
        return {"id": object_id}

    def place_instance(self, object_id, instance, x, y):
        self._rec("place_instance", object_id, instance, x, y)

    def arrange_plate(self):
        self._rec("arrange_plate")
        return [Footprint(1, 0, 20, 20, (125, 105), False)]

    def slice(self, output=None):
        self._rec("slice", output)
        m = GcodeMetrics(60, None, 100.0, 1.0, 1.2, 0.1, 10, 0.2, 0.2, "P", "Q", ["F"], {})
        return SliceResult(FIXTURES / "tail_kobra.gcode", m, ["aviso"], Verification(True, ["bed_shape"], [], []),
                           [Footprint(1, 0, 20, 20, (125, 105), False)])

    def export_3mf(self, output):
        self._rec("export_3mf", str(output))
        return Path(output)

    def save_profile_as(self, name, keys=None, overwrite=False):
        self._rec("save_profile_as", name, tuple(keys or ()), overwrite)
        return [Path("print") / f"{name}.ini"]

    def set_variable_layer_height(self, object_id, quality):
        raise EngineCapabilityError("Requiere el motor GUI (v2)")

    def add_height_range_modifier(self, object_id, z_from, z_to, settings):
        raise EngineCapabilityError("Requiere el motor GUI (v2)")

    def preview_layer(self, layer):
        raise EngineCapabilityError("Requiere el motor GUI (v2)")


def data(result: types.CallToolResult):
    text = result.content[0].text
    try:
        return json.loads(text)
    except ValueError:
        return text


@pytest.fixture
def datadir(tmp_path):
    d = tmp_path / "dd"
    (d / "physical_printer").mkdir(parents=True)
    (d / "physical_printer" / "Kobra.ini").write_text(
        "host_type = octoprint\nprint_host = 10.0.0.5\nprinthost_apikey = SECRET\n", encoding="utf-8")
    return d


class OctoState:
    def __init__(self):
        self.job = "a.gcode"
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        if request.url.path == "/api/job" and request.method == "GET":
            return httpx.Response(200, json={"state": "Printing", "job": {"file": {"name": self.job}}, "progress": {}})
        if request.url.path == "/api/printer":
            return httpx.Response(200, json={"temperature": {}})
        return httpx.Response(204)

    def actions(self):
        return [r for r in self.requests if r.method == "POST"]


def server(datadir, *, allow=False, transport=None, engine=None):
    return build_server(engine=engine or FakeEngine(), datadir=datadir, host_transport=transport,
                        allow_print_control=allow)


async def test_tools_registered(datadir):
    async with Client(server(datadir)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == EXPECTED_TOOLS


async def test_state_tools_route_through_engine(datadir):
    e = FakeEngine()
    async with Client(server(datadir, engine=e)) as c:
        await c.call_tool("select_profiles", {"printer": "P", "print_profile": "Q", "filaments": ["F"]})
        await c.call_tool("set_setting", {"key": "fill_density", "value": "20%"})
        await c.call_tool("reset_setting", {"key": "fill_density"})
        await c.call_tool("add_model", {"path": "x.stl", "copies": 2})
        await c.call_tool("transform_object", {"object_id": 1, "rotate_z": 45})
        await c.call_tool("place_instance", {"object_id": 1, "instance": 0, "x": 10, "y": 20})
        await c.call_tool("arrange_plate", {})
        await c.call_tool("remove_object", {"object_id": 1})
        await c.call_tool("clear_plate", {})
        await c.call_tool("save_profile_as", {"name": "Mio"})
    assert [call[0] for call in e.calls] == [
        "select_profiles", "set_setting", "reset_setting", "add_model", "transform_object", "place_instance",
        "arrange_plate", "remove_object", "clear_plate", "save_profile_as"]
    assert e.calls[4] == ("transform_object", 1, (("rotate_z", 45.0),))


async def test_slice_returns_verification(datadir):
    async with Client(server(datadir)) as c:
        r = data(await c.call_tool("slice", {}))
    assert r["verification"]["ok"] is True and r["placements"][0]["center"] == [125, 105]
    assert r["gcode_path"].endswith("tail_kobra.gcode") and r["warnings"] == ["aviso"]


async def test_v2_tool_error_message(datadir):
    async with Client(server(datadir)) as c:
        r = await c.call_tool("preview_layer", {"layer": 3})
    assert r.is_error and "v2" in r.content[0].text


async def test_gcode_analysis_tools(datadir):
    async with Client(server(datadir)) as c:
        m = data(await c.call_tool("get_gcode_metrics", {"gcode_path": str(FIXTURES / "tail_kobra.gcode")}))
        t = data(await c.call_tool("analyze_toolpaths", {"gcode_path": str(FIXTURES / "mini.gcode")}))
    assert m["print_time_s"] == 871 and "config" not in m
    assert t["confidence"] == "high" and "layers" not in t and t["layer_count"] == 2


async def test_list_print_hosts_hides_secrets(datadir):
    async with Client(server(datadir)) as c:
        r = await c.call_tool("list_print_hosts", {})
    assert "SECRET" not in r.content[0].text
    assert data(r)["hosts"][0]["name"] == "Kobra"


async def test_print_control_disabled_by_default(datadir):
    octo = OctoState()
    async with Client(server(datadir, transport=httpx.MockTransport(octo))) as c:
        r = await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode"})
    assert r.is_error and "PRUSASLICER_MCP_ALLOW_PRINT_CONTROL" in r.content[0].text
    assert octo.actions() == []


async def test_start_print_two_step(datadir):
    octo = OctoState()
    async with Client(server(datadir, allow=True, transport=httpx.MockTransport(octo))) as c:
        first = data(await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode"}))
        assert first["status"] == "confirmation_required" and octo.actions() == []
        await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode", "confirmation_code": first["code"]})
    assert [r.url.path for r in octo.actions()] == ["/api/files/local/a.gcode"]


async def test_start_print_bad_code(datadir):
    octo = OctoState()
    async with Client(server(datadir, allow=True, transport=httpx.MockTransport(octo))) as c:
        r = await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode", "confirmation_code": "zzz"})
    assert r.is_error and octo.actions() == []


async def test_cancel_code_bound_to_job(datadir):
    octo = OctoState()
    async with Client(server(datadir, allow=True, transport=httpx.MockTransport(octo))) as c:
        first = data(await c.call_tool("cancel_print", {"host": "Kobra"}))
        octo.job = "otro.gcode"
        r = await c.call_tool("cancel_print", {"host": "Kobra", "confirmation_code": first["code"]})
    assert r.is_error and octo.actions() == []


def _elicit(action, confirm):
    async def cb(context, params):
        return types.ElicitResult(action=action, content={"confirm": confirm} if action == "accept" else None)

    return cb


async def test_start_print_elicitation_accept(datadir):
    octo = OctoState()
    async with Client(server(datadir, allow=True, transport=httpx.MockTransport(octo)),
                      elicitation_callback=_elicit("accept", True)) as c:
        r = await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode"})
    assert not r.is_error and [x.url.path for x in octo.actions()] == ["/api/files/local/a.gcode"]


async def test_start_print_elicitation_decline(datadir):
    octo = OctoState()
    async with Client(server(datadir, allow=True, transport=httpx.MockTransport(octo)),
                      elicitation_callback=_elicit("decline", False)) as c:
        r = await c.call_tool("start_print", {"host": "Kobra", "remote": "a.gcode"})
    assert r.is_error and octo.actions() == []


async def test_confirmation_answer_not_exposed_to_model(datadir):
    async with Client(server(datadir)) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    for name in ("start_print", "pause_print", "resume_print", "cancel_print"):
        props = tools[name].input_schema["properties"]
        assert "answer" not in props and "confirmation_code" in props
        assert tools[name].annotations.destructive_hint is True
