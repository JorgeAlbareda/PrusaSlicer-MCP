"""Locate a PrusaSlicer installation and read its version."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from prusaslicer_mcp.errors import SlicerNotFoundError

_VERSION_RE = re.compile(r"PrusaSlicer-(\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class SlicerInstall:
    console: Path
    gui: Path | None
    gcodeviewer: Path | None
    resources: Path | None
    version: str


def _exe_names() -> dict[str, str]:
    if sys.platform == "win32":
        return {
            "console": "prusa-slicer-console.exe",
            "gui": "prusa-slicer.exe",
            "gcodeviewer": "prusa-gcodeviewer.exe",
        }
    if sys.platform == "darwin":
        return {"console": "PrusaSlicer", "gui": "PrusaSlicer", "gcodeviewer": "PrusaGCodeViewer"}
    return {"console": "prusa-slicer", "gui": "prusa-slicer", "gcodeviewer": "prusa-gcodeviewer"}


def candidate_dirs() -> list[Path]:
    """Standard install locations for the current platform (only Windows is tested)."""
    if sys.platform == "win32":
        dirs = []
        for var in ("ProgramFiles", "ProgramW6432"):
            if os.environ.get(var):
                dirs.append(Path(os.environ[var]) / "Prusa3D" / "PrusaSlicer")
        if os.environ.get("LOCALAPPDATA"):
            dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PrusaSlicer")
        return dirs
    if sys.platform == "darwin":
        return [
            Path("/Applications/PrusaSlicer.app/Contents/MacOS"),
            Path.home() / "Applications/PrusaSlicer.app/Contents/MacOS",
        ]
    return [Path("/usr/bin"), Path("/usr/local/bin"), Path.home() / "Applications"]


def is_supported_version(version: str) -> bool:
    return version.startswith("2.9.")


def _read_version(console: Path) -> str:
    try:
        out = subprocess.run(
            [str(console), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SlicerNotFoundError(f"No se pudo ejecutar {console}: {e}") from e
    m = _VERSION_RE.search(out.stdout + out.stderr)
    return m.group(1) if m else "unknown"


def _from_dir(d: Path) -> SlicerInstall | None:
    names = _exe_names()
    console = d / names["console"]
    if not console.is_file():
        return None
    gui = d / names["gui"]
    viewer = d / names["gcodeviewer"]
    resources = d / "resources"
    return SlicerInstall(
        console=console,
        gui=gui if gui.is_file() else None,
        gcodeviewer=viewer if viewer.is_file() else None,
        resources=resources if resources.is_dir() else None,
        version=_read_version(console),
    )


def find_installation(override: str | Path | None = None) -> SlicerInstall:
    """Find PrusaSlicer: explicit override, then PRUSASLICER_PATH, then standard dirs."""
    tried: list[Path] = []
    explicit = override or os.environ.get("PRUSASLICER_PATH")
    dirs = [Path(explicit)] if explicit else candidate_dirs()
    for d in dirs:
        if d.is_file():
            d = d.parent
        tried.append(d)
        found = _from_dir(d)
        if found:
            return found
    raise SlicerNotFoundError(
        "No se encontró PrusaSlicer. Instálalo o indica su carpeta con la variable "
        f"PRUSASLICER_PATH. Rutas probadas: {', '.join(str(t) for t in tried) or 'ninguna'}"
    )
