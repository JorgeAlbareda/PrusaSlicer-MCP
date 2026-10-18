"""PrusaSlicer data directory: listing presets, resolving their values, writing user presets."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from prusaslicer_mcp.errors import PrusaMcpError
from prusaslicer_mcp.ini import dump_flat, parse_bundle, parse_flat
from prusaslicer_mcp.install import SlicerInstall
from prusaslicer_mcp.runner import run_cli

Kind = Literal["print", "filament", "printer"]
KINDS: tuple[Kind, ...] = ("print", "filament", "printer")
_BAD_NAME_RE = re.compile(r'[/\\:*?"<>|]')
# Keys never imported from foreign bundles; post_process can run arbitrary programs.
_IMPORT_DROP = ("Hostname", "post_process_enable")


def default_datadir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PrusaSlicer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PrusaSlicer"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "PrusaSlicer"


@dataclass
class PrinterInfo:
    name: str
    vendor: str
    model: str
    extruders: int
    bed_width: float
    bed_depth: float
    max_height: float
    user: bool


@dataclass
class PrintProfileInfo:
    name: str
    user: bool
    filaments: list[str] = field(default_factory=list)


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _query_json(install: SlicerInstall, datadir: Path, args: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="psmcp-") as tmp:
        out = Path(tmp) / "query.json"
        # The query actions exit with code 1 even on success: judge by the output file.
        res = run_cli(install, ["--datadir", datadir, *args, "-o", out], timeout=120, check=False)
        if not out.exists():
            detail = "\n".join(res.errors) or (res.stderr or res.stdout).strip()[-1000:]
            raise PrusaMcpError(f"PrusaSlicer no devolvió resultado para {' '.join(map(str, args))}:\n{detail}")
        return json.loads(out.read_text(encoding="utf-8"))


def _printer_from_json(p: dict, model: dict, user: bool) -> PrinterInfo:
    bed = p.get("bed") or {}
    return PrinterInfo(
        name=str(p["name"]),
        vendor=str(model.get("vendor_name", "")),
        model=str(model.get("id", "")),
        extruders=int(p.get("extruders_cnt", 1)),
        bed_width=float(bed.get("width", 0)),
        bed_depth=float(bed.get("height", 0)),
        max_height=float(bed.get("max_print_height", 0)),
        user=user,
    )


def list_printers(install: SlicerInstall, datadir: Path) -> list[PrinterInfo]:
    data = _query_json(install, datadir, ["--query-printer-models"])
    printers: list[PrinterInfo] = []
    for model in _as_list(data.get("printer_models")):
        undef_vendor = not model.get("vendor_id")
        holders = _as_list(model.get("variants")) or [model]
        for h in holders:
            for p in _as_list(h.get("printer_profiles")):
                printers.append(_printer_from_json(p, model, user=undef_vendor))
            for p in _as_list(h.get("user_printer_profiles")):
                printers.append(_printer_from_json(p, model, user=True))
    return printers


def list_compatible_profiles(install: SlicerInstall, datadir: Path, printer: str) -> list[PrintProfileInfo]:
    data = _query_json(install, datadir, ["--printer-profile", printer, "--query-print-filament-profiles"])
    result: list[PrintProfileInfo] = []
    for key, user in (("print_profiles", False), ("user_print_profiles", True)):
        for p in _as_list(data.get(key)):
            filaments = [str(f) for f in _as_list(p.get("filament_profiles"))]
            filaments += [str(f) for f in _as_list(p.get("user_filament_profiles"))]
            result.append(PrintProfileInfo(name=str(p["name"]), user=user, filaments=filaments))
    return result


def save_user_preset(
    datadir: Path, kind: Kind, name: str, values: dict[str, str], *, overwrite: bool = False
) -> Path:
    if kind not in KINDS:
        raise PrusaMcpError(f"Tipo de perfil no válido: {kind}")
    if not name.strip() or _BAD_NAME_RE.search(name):
        raise PrusaMcpError(f"Nombre de perfil no válido: '{name}'")
    folder = Path(datadir) / kind
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.ini"
    if target.exists():
        if not overwrite:
            raise PrusaMcpError(f"Ya existe el perfil de usuario '{name}' ({kind}). Usa overwrite para reemplazarlo.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(target, folder / f"{name}.ini.bak-{stamp}")
    tmp = folder / f"{name}.ini.tmp"
    tmp.write_text(dump_flat(values), encoding="utf-8")
    os.replace(tmp, target)
    return target


def _parents(values: dict[str, str]) -> list[str]:
    return [p.strip().strip('"') for p in values.get("inherits", "").split(";") if p.strip()]


def _resolve(sections: dict[str, dict[str, str]], name: str, missing: list[str], stack=()) -> dict[str, str]:
    if name in stack:
        raise PrusaMcpError(f"Herencia circular en perfiles: {' -> '.join((*stack, name))}")
    own = sections[name]
    result: dict[str, str] = {}
    for parent in _parents(own):
        if parent in sections:
            result.update(_resolve(sections, parent, missing, (*stack, name)))
        else:
            missing.append(parent)
    result.update({k: v for k, v in own.items() if k != "inherits"})
    return result


def import_bundle(
    datadir: Path, bundle_text: str, *, overwrite: bool = False, allow_post_process: bool = False
) -> tuple[list[Path], list[str]]:
    bundle = parse_bundle(bundle_text)
    paths: list[Path] = []
    warnings: list[str] = []
    for kind in KINDS:
        sections = bundle.get(kind, {})
        for name in sections:
            if name.startswith("*"):  # abstract template, only used for inheritance
                continue
            missing: list[str] = []
            values = _resolve(sections, name, missing)
            if missing:
                values["inherits"] = "; ".join(missing)
                warnings.append(f"{kind} '{name}': hereda de '{'; '.join(missing)}', que no está en el bundle.")
            dropped = [k for k in _IMPORT_DROP if k in values]
            if not allow_post_process and values.get("post_process"):
                dropped.append("post_process")
            for k in dropped:
                values.pop(k, None)
            if dropped:
                warnings.append(f"{kind} '{name}': claves omitidas: {', '.join(dropped)}.")
            paths.append(save_user_preset(datadir, kind, name, values, overwrite=overwrite))
    return paths, warnings


@lru_cache(maxsize=16)
def _vendor_bundle(path: str, mtime: float) -> dict[str, dict[str, dict[str, str]]]:
    return parse_bundle(Path(path).read_text(encoding="utf-8"))


def _vendor_sections(datadir: Path, kind: Kind) -> list[dict[str, dict[str, str]]]:
    result = []
    for f in sorted((Path(datadir) / "vendor").glob("*.ini")):
        result.append(_vendor_bundle(str(f), f.stat().st_mtime).get(kind, {}))
    return result


def resolve_preset_values(
    install: SlicerInstall | None, datadir: Path, kind: Kind, name: str
) -> dict[str, str] | None:
    """Values a preset defines, with `inherits` resolved; None when the preset is not found.

    Keys left at PrusaSlicer defaults are absent, so callers must treat them as unknown.
    """
    vendor = _vendor_sections(datadir, kind)
    user_file = Path(datadir) / kind / f"{name}.ini"
    if user_file.is_file():
        own = parse_flat(user_file.read_text(encoding="utf-8"))
        result: dict[str, str] = {}
        for parent in _parents(own):
            for sections in vendor:
                if parent in sections:
                    result.update(_resolve(sections, parent, []))
                    break
        result.update({k: v for k, v in own.items() if k != "inherits"})
        return result
    for sections in vendor:
        if name in sections:
            return _resolve(sections, name, [])
    return None
