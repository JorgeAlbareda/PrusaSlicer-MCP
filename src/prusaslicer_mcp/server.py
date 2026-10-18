"""MCP server exposing PrusaSlicer through the active Engine (v1: the official CLI).

No `from __future__ import annotations` here: tool signatures use `Resolve(...)` on local
resolvers, which the MCP SDK must be able to evaluate at registration time.
"""

import asyncio
import dataclasses
import functools
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
import httpx
from mcp.server.elicitation import AcceptedElicitation
from mcp.server.mcpserver import Context, Elicit, ElicitationResult, MCPServer, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel

from prusaslicer_mcp import __version__
from prusaslicer_mcp.confirm import CODE_TTL_S, ConfirmationGate
from prusaslicer_mcp.datadir import default_datadir, import_bundle
from prusaslicer_mcp.display import show
from prusaslicer_mcp.engine import Engine
from prusaslicer_mcp.errors import PrusaMcpError
from prusaslicer_mcp.gcode.metrics import get_gcode_metrics
from prusaslicer_mcp.gcode.risks import find_print_risks
from prusaslicer_mcp.gcode.toolpaths import analyze_toolpaths
from prusaslicer_mcp.hosts import HostConfig, load_physical_printers, make_host

INSTRUCTIONS = """Controls PrusaSlicer (unofficial). Typical flow: list_printers -> list_compatible_profiles ->
select_profiles -> add_model -> (transform_object / arrange_plate) -> slice -> find_print_risks ->
show_in_slicer / upload_gcode. Every slice is verified against the requested configuration.
Starting, pausing, resuming or cancelling a physical print needs the user's explicit confirmation:
never confirm on the user's behalf."""

PRINT_CONTROL_DISABLED = (
    "El control de impresión está desactivado. El usuario puede activarlo con "
    "PRUSASLICER_MCP_ALLOW_PRINT_CONTROL=1 en la configuración del servidor."
)


class _Confirm(BaseModel):
    confirm: bool


def _jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _elicitation_supported(ctx: Context) -> bool:
    try:
        caps = ctx.client_capabilities
    except Exception:
        return False
    return caps is not None and getattr(caps, "elicitation", None) is not None


def _default_engine(datadir: Path) -> Engine:
    from prusaslicer_mcp.cli_engine import CliEngine
    from prusaslicer_mcp.install import find_installation

    workdir = Path(os.environ.get("PRUSASLICER_MCP_WORKDIR") or Path(tempfile.gettempdir()) / "prusaslicer-mcp")
    allow_pp = os.environ.get("PRUSASLICER_MCP_ALLOW_POST_PROCESS") == "1"
    return CliEngine(find_installation(), datadir, workdir, allow_post_process=allow_pp)


def build_server(
    engine: Engine | None = None,
    datadir: Path | None = None,
    gate: ConfirmationGate | None = None,
    host_transport: httpx.BaseTransport | None = None,
    allow_print_control: bool | None = None,
) -> MCPServer:
    datadir = Path(datadir or os.environ.get("PRUSASLICER_DATADIR") or default_datadir())
    gate = gate or ConfirmationGate()
    if allow_print_control is None:
        allow_print_control = os.environ.get("PRUSASLICER_MCP_ALLOW_PRINT_CONTROL") == "1"
    lock = asyncio.Lock()
    state: dict[str, Engine] = {}

    def get_engine() -> Engine:
        if "engine" not in state:
            state["engine"] = engine if engine is not None else _default_engine(datadir)
        return state["engine"]

    async def run(fn: Callable, *args, mutate: bool = False, **kw) -> Any:
        """Run blocking work off the event loop; state changes are serialized."""
        call = functools.partial(fn, *args, **kw)
        try:
            if mutate:
                async with lock:
                    return _jsonable(await anyio.to_thread.run_sync(call))
            return _jsonable(await anyio.to_thread.run_sync(call))
        except PrusaMcpError as e:
            raise ToolError(e.message) from e

    def eng(method: str) -> Callable:
        return lambda *a, **k: getattr(get_engine(), method)(*a, **k)

    def find_host(name: str) -> HostConfig:
        hosts = load_physical_printers(datadir)
        for h in hosts:
            if h.name == name:
                return h
        known = ", ".join(h.name for h in hosts) or "ninguna"
        raise PrusaMcpError(f"No hay ninguna impresora física llamada '{name}'. Configuradas: {known}.")

    def host_client(name: str):
        return make_host(find_host(name), host_transport)

    mcp = MCPServer("prusaslicer-mcp", version=__version__, instructions=INSTRUCTIONS)

    # ------------------------------------------------------------ info & profiles
    @mcp.tool()
    async def get_slicer_info() -> dict:
        """PrusaSlicer version and paths, data directory, active engine and whether printer control is enabled."""
        info = await run(eng("info"))
        return {**info, "datadir": str(datadir), "print_control_enabled": allow_print_control}

    @mcp.tool()
    async def list_printers() -> dict:
        """Printer profiles installed in the user's PrusaSlicer (system and user)."""
        return {"printers": await run(eng("list_printers"))}

    @mcp.tool()
    async def list_compatible_profiles(printer: str) -> dict:
        """Print profiles compatible with a printer, each with its compatible filament profiles."""
        return {"printer": printer, "print_profiles": await run(eng("list_compatible_profiles"), printer)}

    @mcp.tool()
    async def select_profiles(printer: str, print_profile: str, filaments: list[str]) -> dict:
        """Select the printer, print and filament profiles to slice with (by exact name)."""
        warnings = await run(eng("select_profiles"), printer, print_profile, filaments, mutate=True)
        return {"selected": {"printer": printer, "print_profile": print_profile, "filaments": filaments}, "warnings": warnings}

    @mcp.tool()
    async def use_config_file(path: str) -> dict:
        """Slice with a flat PrusaSlicer .ini config instead of named profiles (bundles are rejected)."""
        await run(eng("use_config_file"), Path(path), mutate=True)
        return {"config_file": path}

    # ------------------------------------------------------------------- settings
    @mcp.tool()
    async def get_setting(key: str) -> dict:
        """Value of a setting: the session override, else the effective value of the last slice."""
        value = await run(eng("get_setting"), key)
        note = None if value is not None else "lamina primero para ver el valor efectivo"
        return {"key": key, "value": value, "note": note}

    @mcp.tool()
    async def set_setting(key: str, value: str) -> dict:
        """Override a PrusaSlicer setting for this session (e.g. fill_density=20%, layer_height=0.15)."""
        await run(eng("set_setting"), key, value, mutate=True)
        return {"key": key, "value": value}

    @mcp.tool()
    async def reset_setting(key: str) -> dict:
        """Remove a session override so the profile value applies again."""
        await run(eng("reset_setting"), key, mutate=True)
        return {"key": key, "reset": True}

    @mcp.tool()
    async def save_profile_as(name: str, keys: list[str] | None = None, overwrite: bool = False) -> dict:
        """Save the session overrides as user profiles named `name` (one per affected kind), inheriting the selected ones."""
        paths = await run(eng("save_profile_as"), name, keys, overwrite, mutate=True)
        return {"written": paths}

    @mcp.tool()
    async def import_profile_bundle(path: str, overwrite: bool = False) -> dict:
        """Import a PrusaSlicer config bundle (.ini with [print:…] sections) as user profiles."""
        text = Path(path).read_text(encoding="utf-8")
        allow_pp = os.environ.get("PRUSASLICER_MCP_ALLOW_POST_PROCESS") == "1"
        paths, warnings = await run(import_bundle, datadir, text, overwrite=overwrite, allow_post_process=allow_pp, mutate=True)
        return {"written": paths, "warnings": warnings}

    # ---------------------------------------------------------------------- plate
    @mcp.tool()
    async def add_model(path: str, copies: int = 1) -> dict:
        """Add a model file (STL, 3MF, OBJ, STEP, AMF) to the bed; returns its id and size."""
        return await run(eng("add_model"), Path(path), copies, mutate=True)

    @mcp.tool()
    async def get_plate() -> dict:
        """Current bed: selected profiles, setting overrides and objects with their instances."""
        return await run(eng("get_plate"))

    @mcp.tool()
    async def remove_object(object_id: int) -> dict:
        """Remove an object from the bed."""
        await run(eng("remove_object"), object_id, mutate=True)
        return {"removed": object_id}

    @mcp.tool()
    async def clear_plate() -> dict:
        """Remove every object from the bed."""
        await run(eng("clear_plate"), mutate=True)
        return {"cleared": True}

    @mcp.tool()
    async def transform_object(
        object_id: int,
        rotate_z: float | None = None,
        rotate_x: float | None = None,
        rotate_y: float | None = None,
        scale_percent: float | None = None,
        copies: int | None = None,
    ) -> dict:
        """Set absolute rotation (degrees), scale (%) and number of copies of an object."""
        kw = {k: v for k, v in dict(rotate_z=rotate_z, rotate_x=rotate_x, rotate_y=rotate_y,
                                    scale_percent=scale_percent, copies=copies).items() if v is not None}
        return await run(eng("transform_object"), object_id, mutate=True, **kw)

    @mcp.tool()
    async def place_instance(object_id: int, instance: int, x: float, y: float) -> dict:
        """Fix the centre (mm) of one copy of an object on the bed."""
        await run(eng("place_instance"), object_id, instance, x, y, mutate=True)
        return {"object_id": object_id, "instance": instance, "center": [x, y]}

    @mcp.tool()
    async def arrange_plate() -> dict:
        """Automatically place every copy that the user has not fixed; returns the positions."""
        return {"placements": await run(eng("arrange_plate"), mutate=True)}

    # -------------------------------------------------------------------- slicing
    @mcp.tool()
    async def slice(output_path: str | None = None) -> dict:
        """Slice the bed. Returns the G-code path, metrics, warnings, placements and the configuration check."""
        r = await run(eng("slice"), Path(output_path) if output_path else None, mutate=True)
        r["metrics"].pop("config", None)
        return r

    @mcp.tool()
    async def export_3mf(output_path: str) -> dict:
        """Export the bed (objects, positions and configuration) as a 3MF project."""
        return {"path": await run(eng("export_3mf"), Path(output_path), mutate=True)}

    # ------------------------------------------------------------------- analysis
    @mcp.tool()
    async def get_gcode_metrics(gcode_path: str) -> dict:
        """Print time, filament (mm, cm³, g), cost, layers and profiles of a PrusaSlicer G-code."""
        m = await run(get_gcode_metrics_fn, Path(gcode_path))
        m.pop("config", None)
        return m

    @mcp.tool()
    async def analyze_toolpaths(gcode_path: str, include_layers: bool = False, max_layers: int = 50) -> dict:
        """Time and material per move type (perimeters, infill, bridges, travel…); optionally the slowest layers."""
        rep = await run(analyze_toolpaths_fn, Path(gcode_path))
        layers = rep.pop("layers")
        rep["layer_count"] = len(layers)
        rep["time_note"] = "Tiempos estimados por velocidad y reescalados al total de PrusaSlicer (aproximados)."
        if include_layers:
            rep["layers"] = sorted(layers, key=lambda lay: -lay["time_s"])[:max_layers]
        return rep

    @mcp.tool()
    async def find_print_risks(gcode_path: str) -> dict:
        """Possible print problems (warping, overhangs, long bridges, flow or machine limits…) with evidence."""

        def risks(p: Path):
            return find_print_risks_fn(analyze_toolpaths_fn(p), get_gcode_metrics_fn(p).config)

        return {"risks": await run(risks, Path(gcode_path))}

    # ---------------------------------------------------------------------- view
    @mcp.tool()
    async def show_in_slicer(path: str) -> dict:
        """Open a model/3MF in the user's PrusaSlicer window, or a G-code in the G-code viewer."""

        def _show(p: Path):
            show(get_engine().install, p)  # type: ignore[attr-defined]

        await run(_show, Path(path))
        return {"opened": path}

    # ------------------------------------------------------------------ v2 only
    @mcp.tool()
    async def set_variable_layer_height(object_id: int, quality: float = 0.5) -> dict:
        """Adaptive variable layer height for an object (GUI engine, v2)."""
        await run(eng("set_variable_layer_height"), object_id, quality, mutate=True)
        return {"ok": True}

    @mcp.tool()
    async def add_height_range_modifier(object_id: int, z_from: float, z_to: float, settings: dict[str, str]) -> dict:
        """Different settings for a height range of an object (GUI engine, v2)."""
        await run(eng("add_height_range_modifier"), object_id, z_from, z_to, settings, mutate=True)
        return {"ok": True}

    @mcp.tool()
    async def preview_layer(layer: int) -> dict:
        """Show a given layer in the live preview (GUI engine, v2)."""
        await run(eng("preview_layer"), layer)
        return {"ok": True}

    # ------------------------------------------------------------------ printers
    @mcp.tool()
    async def list_print_hosts() -> dict:
        """Networked printers configured in PrusaSlicer (OctoPrint, Moonraker/Klipper, PrusaLink). No secrets."""
        return {"hosts": [h.public() for h in await anyio.to_thread.run_sync(load_physical_printers, datadir)]}

    @mcp.tool()
    async def upload_gcode(host: str, gcode_path: str) -> dict:
        """Upload a G-code to a networked printer without starting it. Returns the remote path."""
        return {"remote": await run(lambda: host_client(host).upload(Path(gcode_path), start=False))}

    @mcp.tool()
    async def get_printer_status(host: str) -> dict:
        """State, progress, current file and temperatures of a networked printer."""
        st = await run(lambda: host_client(host).status())
        st.pop("raw", None)
        return st

    labels = {"start_print": "Iniciar", "pause_print": "Pausar", "resume_print": "Reanudar", "cancel_print": "Cancelar"}

    async def describe(action: str, host: str, remote: str | None) -> tuple[dict, str]:
        """Parameters the approval is bound to (printer + file, or printer + current job) and the question."""
        if remote is not None:
            params, what = {"host": host, "remote": remote}, f"'{remote}'"
        else:
            status = await run(lambda: host_client(host).status())
            if not status["job_id"]:
                raise ToolError(f"'{host}' no tiene ningún trabajo en curso.")
            params, what = {"host": host, "job_id": status["job_id"]}, f"el trabajo '{status['job_id']}'"
        return params, f"¿{labels[action]} {what} en la impresora '{host}'?"

    def make_ask(action: str, with_remote: bool) -> Callable:
        """Resolver that asks the human through elicitation when the client supports it."""

        async def ask_job(host: str, ctx: Context) -> Elicit[_Confirm] | None:
            if not allow_print_control or not _elicitation_supported(ctx):
                return None
            _, summary = await describe(action, host, None)
            return Elicit(summary, _Confirm)

        async def ask_file(host: str, remote: str, ctx: Context) -> Elicit[_Confirm] | None:
            if not allow_print_control or not _elicitation_supported(ctx):
                return None
            _, summary = await describe(action, host, remote)
            return Elicit(summary, _Confirm)

        return ask_file if with_remote else ask_job

    async def controlled(
        action: str, host: str, remote: str | None, answer: ElicitationResult, code: str | None, do: Callable
    ) -> dict:
        if not allow_print_control:
            raise ToolError(PRINT_CONTROL_DISABLED)
        params, summary = await describe(action, host, remote)
        elicited = not (isinstance(answer, AcceptedElicitation) and answer.data is None)
        if elicited:
            if not (isinstance(answer, AcceptedElicitation) and answer.data.confirm):
                raise ToolError("El usuario no ha confirmado la acción; no se ha hecho nada.")
        elif code is None:
            return {
                "status": "confirmation_required",
                "code": gate.request(action, params),
                "expires_in_s": CODE_TTL_S,
                "summary": summary,
                "instructions": "Pregunta al usuario y, solo si acepta explícitamente, vuelve a llamar con "
                "confirmation_code. Esta confirmación depende del cliente.",
            }
        else:
            try:
                gate.consume(code, action, params)
            except PrusaMcpError as e:
                raise ToolError(e.message) from e
        await run(do, mutate=True)
        return {"status": "done", "action": action, **params}

    destructive = ToolAnnotations(destructive_hint=True)
    ask_start = make_ask("start_print", True)
    ask_pause = make_ask("pause_print", False)
    ask_resume = make_ask("resume_print", False)
    ask_cancel = make_ask("cancel_print", False)

    @mcp.tool(annotations=destructive)
    async def start_print(
        host: str,
        remote: str,
        answer: Annotated[ElicitationResult[_Confirm], Resolve(ask_start)],
        confirmation_code: str | None = None,
    ) -> dict:
        """Start printing an already uploaded file. Needs the user's explicit confirmation."""
        return await controlled("start_print", host, remote, answer, confirmation_code, lambda: host_client(host).start(remote))

    @mcp.tool(annotations=destructive)
    async def pause_print(
        host: str,
        answer: Annotated[ElicitationResult[_Confirm], Resolve(ask_pause)],
        confirmation_code: str | None = None,
    ) -> dict:
        """Pause the current print. Needs the user's explicit confirmation."""
        return await controlled("pause_print", host, None, answer, confirmation_code, lambda: host_client(host).pause())

    @mcp.tool(annotations=destructive)
    async def resume_print(
        host: str,
        answer: Annotated[ElicitationResult[_Confirm], Resolve(ask_resume)],
        confirmation_code: str | None = None,
    ) -> dict:
        """Resume a paused print. Needs the user's explicit confirmation."""
        return await controlled("resume_print", host, None, answer, confirmation_code, lambda: host_client(host).resume())

    @mcp.tool(annotations=destructive)
    async def cancel_print(
        host: str,
        answer: Annotated[ElicitationResult[_Confirm], Resolve(ask_cancel)],
        confirmation_code: str | None = None,
    ) -> dict:
        """Cancel the current print. Needs the user's explicit confirmation."""
        return await controlled("cancel_print", host, None, answer, confirmation_code, lambda: host_client(host).cancel())

    return mcp


get_gcode_metrics_fn = get_gcode_metrics
analyze_toolpaths_fn = analyze_toolpaths
find_print_risks_fn = find_print_risks


def main() -> None:
    build_server().run()


__all__: list[Literal["build_server", "main"]] = ["build_server", "main"]
