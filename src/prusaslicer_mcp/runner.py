"""Run prusa-slicer-console and classify what it prints."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from prusaslicer_mcp.errors import CliError, CliTimeoutError
from prusaslicer_mcp.install import SlicerInstall

_PROGRESS_RE = re.compile(r"^\s*\d+\s*=>")
_REMOVED_KEYS_RE = re.compile(r"contains the following incorrect keys: .* which were removed")
_ERROR_MARKERS = ("wasn't found", "incompatible", "Error", "error:", "[error]", "[fatal]")
_BLOCK_END_RE = re.compile(r"^(Slicing result exported|Output for your request|File exported)")


@dataclass
class CliResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    warnings: list[str]
    errors: list[str]


def classify_output(text: str) -> tuple[list[str], list[str]]:
    """Split PrusaSlicer console output into (warnings, errors); progress lines are dropped."""
    warnings: list[str] = []
    errors: list[str] = []
    block: list[str] | None = None

    def close_block():
        nonlocal block
        if block:
            warnings.append("\n".join(block))
        block = None

    for raw in text.splitlines():
        line = raw.strip()
        if _PROGRESS_RE.match(line) or _BLOCK_END_RE.match(line):
            close_block()
            continue
        if line.startswith("Print warning:"):
            close_block()
            block = [line]
            continue
        if block is not None:
            if line:
                block.append(line)
            continue
        if not line:
            continue
        if _REMOVED_KEYS_RE.search(line) or "[warning]" in line:
            warnings.append(line)
        elif any(m in line for m in _ERROR_MARKERS):
            errors.append(line)
    close_block()
    return warnings, errors


def run_cli(
    install: SlicerInstall,
    args: list[str],
    *,
    timeout: float = 600,
    cwd: Path | None = None,
) -> CliResult:
    cmd = [str(install.console), *[str(a) for a in args]]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as e:
        raise CliTimeoutError(f"PrusaSlicer no terminó en {timeout:.0f} s y se ha detenido.") from e
    warnings, errors = classify_output(proc.stdout + "\n" + proc.stderr)
    result = CliResult(cmd, proc.returncode, proc.stdout, proc.stderr, warnings, errors)
    if proc.returncode != 0:
        detail = "\n".join(errors) or (proc.stderr or proc.stdout).strip()[-2000:]
        raise CliError(f"PrusaSlicer falló (código {proc.returncode}):\n{detail}")
    return result
