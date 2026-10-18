"""Open results in the user's PrusaSlicer window or in the G-code viewer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from prusaslicer_mcp.errors import PrusaMcpError, SlicerNotFoundError
from prusaslicer_mcp.install import SlicerInstall

MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".amf"}
GCODE_EXTENSIONS = {".gcode", ".gco", ".g"}


def viewer_command(install: SlicerInstall, path: Path) -> list[str]:
    ext = Path(path).suffix.lower()
    if ext not in MODEL_EXTENSIONS | GCODE_EXTENSIONS:
        raise PrusaMcpError(f"No sé abrir archivos '{ext}' en PrusaSlicer.")
    if ext in GCODE_EXTENSIONS and install.gcodeviewer:
        return [str(install.gcodeviewer), str(path)]
    if install.gui is None:
        raise SlicerNotFoundError("No se encontró la aplicación gráfica de PrusaSlicer.")
    if ext in GCODE_EXTENSIONS:
        return [str(install.gui), "--gcodeviewer", str(path)]
    # reuse the window the user already has open
    return [str(install.gui), "--single-instance", str(path)]


def show(install: SlicerInstall, path: Path) -> None:
    cmd = viewer_command(install, path)
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
