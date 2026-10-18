import json

import httpx
import pytest

from prusaslicer_mcp.errors import HostError
from prusaslicer_mcp.hosts import HostConfig, load_physical_printers, make_host


class Recorder:
    """httpx MockTransport that records requests and answers from a route table."""

    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        handler = self.routes.get(key)
        if handler is None:
            return httpx.Response(404, json={"error": f"no route {key}"})
        return handler(request) if callable(handler) else httpx.Response(200, json=handler)

    def last(self, method, path):
        return [r for r in self.requests if r.method == method and r.url.path == path][-1]


def cfg(host_type, **kw):
    base = dict(name="P", host_type=host_type, url="http://printer.local", api_key="KEY", user=None,
                password=None, auth="key", cafile=None)
    base.update(kw)
    return HostConfig(**base)


@pytest.fixture
def gcode(tmp_path):
    p = tmp_path / "pieza.gcode"
    p.write_bytes(b"G28\n")
    return p


# ------------------------------------------------------------------ OctoPrint
OCTO = {
    ("POST", "/api/files/local"): {"files": {"local": {"name": "pieza.gcode"}}, "done": True},
    ("POST", "/api/files/local/pieza.gcode"): lambda r: httpx.Response(204),
    ("GET", "/api/job"): {"job": {"file": {"name": "pieza.gcode"}}, "progress": {"completion": 42.0}, "state": "Printing"},
    ("GET", "/api/printer"): {"temperature": {"tool0": {"actual": 214.8}, "bed": {"actual": 60.1}}},
    ("POST", "/api/job"): lambda r: httpx.Response(204),
}


def test_octoprint_upload_no_start(gcode):
    rec = Recorder(OCTO)
    remote = make_host(cfg("octoprint"), httpx.MockTransport(rec)).upload(gcode)
    req = rec.last("POST", "/api/files/local")
    assert remote == "pieza.gcode"
    assert req.headers["X-Api-Key"] == "KEY"
    assert b'name="print"\r\n\r\nfalse' in req.content


def test_octoprint_upload_start(gcode):
    rec = Recorder(OCTO)
    make_host(cfg("octoprint"), httpx.MockTransport(rec)).upload(gcode, start=True)
    assert b'name="print"\r\n\r\ntrue' in rec.last("POST", "/api/files/local").content


def test_octoprint_status_and_controls():
    rec = Recorder(OCTO)
    h = make_host(cfg("octoprint"), httpx.MockTransport(rec))
    s = h.status()
    assert (s.state, s.progress, s.file, s.nozzle_temp, s.bed_temp, s.job_id) == (
        "Printing", 42.0, "pieza.gcode", 214.8, 60.1, "pieza.gcode")
    h.start("pieza.gcode")
    assert json.loads(rec.last("POST", "/api/files/local/pieza.gcode").content) == {"command": "select", "print": True}
    h.pause()
    assert json.loads(rec.last("POST", "/api/job").content) == {"command": "pause", "action": "pause"}
    h.resume()
    assert json.loads(rec.last("POST", "/api/job").content) == {"command": "pause", "action": "resume"}
    h.cancel()
    assert json.loads(rec.last("POST", "/api/job").content) == {"command": "cancel"}


def test_unauthorized_is_credentials_error():
    rec = Recorder({("GET", "/api/job"): lambda r: httpx.Response(401)})
    with pytest.raises(HostError) as e:
        make_host(cfg("octoprint"), httpx.MockTransport(rec)).status()
    assert "credenciales" in e.value.message


# ------------------------------------------------------------------ Moonraker
MOON = {
    ("POST", "/server/files/upload"): {"result": {"item": {"path": "sub/pieza.gcode", "root": "gcodes"}, "print_started": False}},
    ("POST", "/printer/print/start"): {"result": "ok"},
    ("GET", "/printer/objects/query"): {"result": {"status": {
        "print_stats": {"state": "printing", "filename": "sub/pieza.gcode"},
        "virtual_sdcard": {"progress": 0.25},
        "extruder": {"temperature": 220.0}, "heater_bed": {"temperature": 65.0}}}},
    ("POST", "/printer/print/pause"): {"result": "ok"},
    ("POST", "/printer/print/resume"): {"result": "ok"},
    ("POST", "/printer/print/cancel"): {"result": "ok"},
}


def test_moonraker_upload_returns_remote_path(gcode):
    rec = Recorder(MOON)
    remote = make_host(cfg("moonraker"), httpx.MockTransport(rec)).upload(gcode)
    assert remote == "sub/pieza.gcode"
    assert b'name="print"\r\n\r\nfalse' in rec.last("POST", "/server/files/upload").content


def test_moonraker_upload_start(gcode):
    rec = Recorder(MOON)
    make_host(cfg("moonraker"), httpx.MockTransport(rec)).upload(gcode, start=True)
    assert b'name="print"\r\n\r\ntrue' in rec.last("POST", "/server/files/upload").content


def test_moonraker_status_and_controls():
    rec = Recorder(MOON)
    h = make_host(cfg("moonraker"), httpx.MockTransport(rec))
    s = h.status()
    assert (s.state, s.progress, s.job_id, s.nozzle_temp) == ("printing", 25.0, "sub/pieza.gcode", 220.0)
    h.start("sub/pieza.gcode")
    assert rec.last("POST", "/printer/print/start").url.params["filename"] == "sub/pieza.gcode"
    h.pause()
    h.resume()
    h.cancel()
    assert [r.url.path for r in rec.requests[-3:]] == ["/printer/print/pause", "/printer/print/resume", "/printer/print/cancel"]


# ------------------------------------------------------------------ PrusaLink
def _link_routes(conflict=False):
    return {
        ("GET", "/api/v1/storage"): {"storage_list": [
            {"path": "/local", "available": False, "read_only": False},
            {"path": "/usb", "available": True, "read_only": False}]},
        ("PUT", "/api/v1/files/usb/pieza.gcode"): (lambda r: httpx.Response(409 if conflict else 201)),
        ("POST", "/api/v1/files/usb/pieza.gcode"): lambda r: httpx.Response(204),
        ("GET", "/api/v1/status"): {"printer": {"state": "PRINTING", "temp_nozzle": 215.0, "temp_bed": 60.0},
                                    "job": {"id": 12, "progress": 40}},
        ("GET", "/api/v1/job"): {"id": 12, "state": "PRINTING", "progress": 40, "file": {"name": "pieza.gcode"}},
        ("PUT", "/api/v1/job/12/pause"): lambda r: httpx.Response(204),
        ("PUT", "/api/v1/job/12/resume"): lambda r: httpx.Response(204),
        ("DELETE", "/api/v1/job/12"): lambda r: httpx.Response(204),
    }


def test_prusalink_upload_headers_and_storage(gcode):
    rec = Recorder(_link_routes())
    remote = make_host(cfg("prusalink"), httpx.MockTransport(rec)).upload(gcode)
    req = rec.last("PUT", "/api/v1/files/usb/pieza.gcode")
    assert remote == "/usb/pieza.gcode"
    assert req.headers["Overwrite"] == "?0" and req.headers["Print-After-Upload"] == "?0"
    assert req.headers["Content-Type"] == "application/octet-stream" and req.content == b"G28\n"
    assert "Overwrite-File" not in req.headers


def test_prusalink_upload_start_header(gcode):
    rec = Recorder(_link_routes())
    make_host(cfg("prusalink"), httpx.MockTransport(rec)).upload(gcode, start=True)
    assert rec.last("PUT", "/api/v1/files/usb/pieza.gcode").headers["Print-After-Upload"] == "?1"


def test_prusalink_configured_storage_skips_discovery(gcode):
    rec = Recorder(_link_routes())
    make_host(cfg("prusalink", storage="/usb"), httpx.MockTransport(rec)).upload(gcode)
    assert not [r for r in rec.requests if r.url.path == "/api/v1/storage"]


def test_prusalink_conflict(gcode):
    rec = Recorder(_link_routes(conflict=True))
    with pytest.raises(HostError) as e:
        make_host(cfg("prusalink"), httpx.MockTransport(rec)).upload(gcode)
    assert "Ya existe" in e.value.message


def test_prusalink_status_and_controls():
    rec = Recorder(_link_routes())
    h = make_host(cfg("prusalink"), httpx.MockTransport(rec))
    s = h.status()
    assert (s.state, s.progress, s.job_id, s.bed_temp) == ("PRINTING", 40.0, "12", 60.0)
    h.start("/usb/pieza.gcode")
    assert rec.requests[-1].method == "POST" and rec.requests[-1].url.path == "/api/v1/files/usb/pieza.gcode"
    h.pause()
    assert rec.requests[-1].url.path == "/api/v1/job/12/pause"
    h.resume()
    h.cancel()
    assert (rec.requests[-1].method, rec.requests[-1].url.path) == ("DELETE", "/api/v1/job/12")


def test_prusalink_digest_auth_used(gcode):
    calls = {"n": 0}

    def put(r):
        calls["n"] += 1
        if "Authorization" not in r.headers:
            return httpx.Response(401, headers={"WWW-Authenticate": 'Digest realm="x", nonce="abc", qop="auth"'})
        return httpx.Response(201)

    routes = _link_routes()
    routes[("PUT", "/api/v1/files/usb/pieza.gcode")] = put
    rec = Recorder(routes)
    h = make_host(cfg("prusalink", auth="user", api_key=None, user="maker", password="pw", storage="/usb"),
                  httpx.MockTransport(rec))
    h.upload(gcode)
    assert rec.requests[-1].headers["Authorization"].startswith("Digest")


# ------------------------------------------------------------------ config
def test_load_physical_printers(tmp_path):
    d = tmp_path / "physical_printer"
    d.mkdir()
    (d / "Kobra (OctoPrint).ini").write_text(
        "host_type = octoprint\nprint_host = 192.168.1.50\nprinthost_apikey = ABC\n"
        "printhost_authorization_type = key\nprinthost_cafile = \npreset_names = \"Anycubic Kobra 2 MAX\"\n",
        encoding="utf-8")
    (h,) = load_physical_printers(tmp_path)
    assert (h.name, h.host_type, h.url, h.api_key, h.auth) == (
        "Kobra (OctoPrint)", "octoprint", "http://192.168.1.50", "ABC", "key")


def test_load_physical_printers_missing_dir(tmp_path):
    assert load_physical_printers(tmp_path) == []


def test_unsupported_host_type():
    with pytest.raises(HostError) as e:
        make_host(cfg("duet"))
    assert "no soportado" in e.value.message
