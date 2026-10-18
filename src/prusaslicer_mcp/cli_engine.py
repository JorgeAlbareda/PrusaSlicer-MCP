"""Engine backed by the official PrusaSlicer command line (v1)."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from prusaslicer_mcp.datadir import (
    PrinterInfo,
    PrintProfileInfo,
    list_compatible_profiles,
    list_printers,
    resolve_preset_values,
    system_preset_values,
    save_user_preset,
)
from prusaslicer_mcp.engine import SliceResult
from prusaslicer_mcp.errors import CliError, EngineCapabilityError, PrusaMcpError, VerificationError
from prusaslicer_mcp.gcode.metrics import get_gcode_metrics
from prusaslicer_mcp.ini import dump_flat, load_flat_file
from prusaslicer_mcp.install import SlicerInstall, is_supported_version
from prusaslicer_mcp.placement import Footprint, pack, parse_bed_polygon, parse_bed_shape, validate
from prusaslicer_mcp.preset_keys import classify_key
from prusaslicer_mcp.runner import run_cli
from prusaslicer_mcp.session import PlateObject, Session
from prusaslicer_mcp.verify import build_expected, compare, expected_ids, read_effective_config, verify

V2_ONLY = "Requiere el motor GUI (v2)"
DEFAULT_SPACING = 6.0
_PROBE_CUBE = """solid probe
""" + "".join(
    f" facet normal 0 0 0\n  outer loop\n" + "".join(f"   vertex {' '.join(map(str, v))}\n" for v in tri) + "  endloop\n endfacet\n"
    for tri in [
        [(0, 0, 0), (10, 10, 0), (10, 0, 0)], [(0, 0, 0), (0, 10, 0), (10, 10, 0)],
        [(0, 0, 10), (10, 0, 10), (10, 10, 10)], [(0, 0, 10), (10, 10, 10), (0, 10, 10)],
        [(0, 0, 0), (10, 0, 0), (10, 0, 10)], [(0, 0, 0), (10, 0, 10), (0, 0, 10)],
        [(10, 0, 0), (10, 10, 0), (10, 10, 10)], [(10, 0, 0), (10, 10, 10), (10, 0, 10)],
        [(10, 10, 0), (0, 10, 0), (0, 10, 10)], [(10, 10, 0), (0, 10, 10), (10, 10, 10)],
        [(0, 10, 0), (0, 0, 0), (0, 0, 10)], [(0, 10, 0), (0, 0, 10), (0, 10, 10)],
    ]
) + "endsolid probe\n"


def _parse_info(stdout: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("["):
            info[key.strip()] = value.strip()
    return info


class CliEngine:
    name = "cli"

    def __init__(self, install: SlicerInstall, datadir: Path, workdir: Path, allow_post_process: bool = False):
        self.install = install
        self.datadir = Path(datadir)
        self.workdir = Path(workdir)
        self.allow_post_process = allow_post_process
        self._session = Session()
        self._last_config: dict[str, str] = {}
        self._proc_dir = self.workdir / str(os.getpid())
        self._cache_dir = self._proc_dir / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- reads
    def info(self) -> dict:
        supported = is_supported_version(self.install.version)
        return {
            "engine": self.name,
            "version": self.install.version,
            "supported_version": supported,
            "warning": None if supported else f"PrusaSlicer {self.install.version} no es 2.9.x; puede fallar.",
            "console": str(self.install.console),
            "gui": str(self.install.gui) if self.install.gui else None,
            "datadir": str(self.datadir),
            "workdir": str(self.workdir),
        }

    def list_printers(self) -> list[PrinterInfo]:
        return list_printers(self.install, self.datadir)

    def list_compatible_profiles(self, printer: str) -> list[PrintProfileInfo]:
        return list_compatible_profiles(self.install, self.datadir, printer)

    def get_plate(self) -> dict:
        return self._session.to_dict()

    def get_setting(self, key: str) -> str | None:
        if key in self._session.overrides:
            return self._session.overrides[key]
        return self._last_config.get(key)

    # -------------------------------------------------------- state changes
    def select_profiles(self, printer: str, print_profile: str, filaments: list[str]) -> list[str]:
        if not filaments:
            raise PrusaMcpError("Indica al menos un perfil de filamento.")
        warnings = []
        if len(filaments) > 1:
            warnings.append("Perfiles multiextrusor no soportados en esta versión: se usará solo el primer filamento.")
        self._session.select_profiles(printer, print_profile, filaments[:1])
        return warnings

    def use_config_file(self, path: Path) -> None:
        load_flat_file(Path(path))  # rejects bundles
        self._session.config_file = Path(path)

    def set_setting(self, key: str, value: str) -> None:
        if key == "post_process" and not self.allow_post_process:
            raise PrusaMcpError(
                "post_process ejecuta programas externos y está bloqueado. "
                "El usuario puede permitirlo con PRUSASLICER_MCP_ALLOW_POST_PROCESS=1."
            )
        self._session.set_setting(key, value)

    def reset_setting(self, key: str) -> None:
        self._session.reset_setting(key)

    def add_model(self, path: Path, copies: int = 1) -> dict:
        obj = self._session.add_object(Path(path), copies)
        try:
            info = self.model_info(obj.path)
        except PrusaMcpError:
            self._session.remove_object(obj.id)
            raise
        return {"object": self._obj_dict(obj), "model_info": info}

    def remove_object(self, object_id: int) -> None:
        self._session.remove_object(object_id)

    def clear_plate(self) -> None:
        self._session.clear()

    def transform_object(self, object_id: int, **kw) -> dict:
        return self._obj_dict(self._session.transform(object_id, **kw))

    def place_instance(self, object_id: int, instance: int, x: float, y: float) -> None:
        self._session.place(object_id, instance, x, y)

    def arrange_plate(self) -> list[Footprint]:
        self._session.unplace_all()
        s = self._session.snapshot()
        placed = self._resolve_placements(s, self._printer_values(s))
        for f in placed:
            inst = self._session.get(f.object_id).instances[f.instance]
            if not inst.fixed:
                inst.center = f.center
        return placed

    # -------------------------------------------------------------- actions
    def model_info(self, path: Path) -> dict[str, str]:
        res = run_cli(self.install, ["--info", path], timeout=120)
        info = _parse_info(res.stdout)
        if "size_x" not in info:
            raise PrusaMcpError(f"PrusaSlicer no pudo leer el modelo '{path}'.")
        return info

    def slice(self, output: Path | None = None) -> SliceResult:
        s = self._session.snapshot()
        job = self._new_job()
        source = self._source_values(s)
        printer_values = self._printer_values(s, source)
        placements = self._resolve_placements(s, printer_values)
        self._check_height(s, printer_values)
        inputs = self._instance_files(s, placements, job)
        out = job / "out.gcode"
        res = run_cli(
            self.install,
            [*self._config_args(s, job), "--no-binary-gcode", *self._merge_args(inputs),
             "--export-gcode", "-o", out, *inputs],
            # PrusaSlicer asks "Continue(Y/N)?" before running a post-processing script
            input="Y\n" if self.allow_post_process else None,
        )
        if not out.exists():
            raise CliError("PrusaSlicer no generó el G-code:\n" + "\n".join(res.errors or [res.stdout[-1000:]]))
        ids = expected_ids(s.printer, s.print_profile, s.filaments) if not s.config_file else {}
        overrides = dict(s.overrides)
        if not self.allow_post_process:
            overrides["post_process"] = ""
        expected, unchecked = build_expected(ids, source, overrides)
        v = verify(out, expected, unchecked)
        if not v.ok:
            detail = "; ".join(f"{m.key}: esperado {m.expected!r}, obtenido {m.actual!r}" for m in v.mismatches)
            raise VerificationError(f"El G-code no usa la configuración pedida ({detail}). Revisión en {out}", v)
        final = Path(output) if output else self._default_output(s)
        publish_file(out, final)
        self._last_config = read_effective_config(final)
        warnings = list(res.warnings)
        warnings += self._multi_extruder_warning(s)
        return SliceResult(final, get_gcode_metrics(final), warnings, v, placements)

    def export_3mf(self, output: Path) -> Path:
        s = self._session.snapshot()
        job = self._new_job()
        placements = self._resolve_placements(s, self._printer_values(s))
        inputs = self._instance_files(s, placements, job)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        run_cli(self.install, [*self._config_args(s, job), *self._merge_args(inputs), "--export-3mf", "-o", output, *inputs])
        if not output.exists():
            raise CliError(f"PrusaSlicer no generó '{output}'.")
        return output

    def save_profile_as(self, name: str, keys: list[str] | None = None, overwrite: bool = False) -> list[Path]:
        s = self._session
        if s.config_file or not (s.printer and s.print_profile and s.filaments):
            raise PrusaMcpError("Para guardar un perfil hay que tener seleccionados perfiles con nombre (select_profiles).")
        chosen = {k: v for k, v in s.overrides.items() if keys is None or k in keys}
        if not chosen:
            raise PrusaMcpError("No hay ajustes modificados que guardar.")
        unknown = [k for k in chosen if classify_key(k) is None]
        if unknown:
            raise PrusaMcpError(f"Claves que no pertenecen a ningún tipo de perfil: {', '.join(unknown)}.")
        kinds = sorted({classify_key(k) for k in chosen})
        taken = [k for k in kinds if system_preset_values(self.datadir, k, name) is not None]
        if taken:
            raise PrusaMcpError(
                f"'{name}' es el nombre de un perfil de sistema ({', '.join(taken)}); PrusaSlicer ignoraría el tuyo. "
                "Elige otro nombre."
            )
        # PrusaSlicer loads a user preset as built-in defaults + the file (`inherits` is only
        # metadata), so the saved preset must hold every key of its kind, not just the changes.
        job = self._new_job()
        changes = job / "changes.ini"
        changes.write_text(dump_flat(chosen), encoding="utf-8")
        full_ini = job / "full.ini"
        run_cli(self.install, ["--datadir", self.datadir, "--printer-profile", s.printer, "--print-profile",
                               s.print_profile, "--material-profile", s.filaments[0], "--load", changes,
                               "--save", full_ini])
        full = load_flat_file(full_ini)
        paths = [
            save_user_preset(self.datadir, kind, name, {k: v for k, v in full.items() if classify_key(k) == kind},
                             overwrite=overwrite)
            for kind in kinds
        ]
        self._probe(
            name if "printer" in kinds else s.printer,
            name if "print" in kinds else s.print_profile,
            name if "filament" in kinds else s.filaments[0],
            expected={k: full[k] for k in (*chosen, "layer_height", "bed_shape", "temperature") if k in full},
        )
        return paths

    def set_variable_layer_height(self, object_id: int, quality: float) -> None:
        raise EngineCapabilityError(V2_ONLY)

    def add_height_range_modifier(self, object_id: int, z_from: float, z_to: float, settings: dict[str, str]) -> None:
        raise EngineCapabilityError(V2_ONLY)

    def preview_layer(self, layer: int) -> None:
        raise EngineCapabilityError(V2_ONLY)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _obj_dict(obj: PlateObject) -> dict:
        d = asdict(obj)
        d["path"] = str(obj.path)
        return d

    def _new_job(self) -> Path:
        job = self._proc_dir / uuid.uuid4().hex
        job.mkdir(parents=True)
        return job

    def _default_output(self, s: Session) -> Path:
        stem = s.objects[0].path.stem if s.objects else "plate"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.workdir / "output" / f"{stem}-{stamp}-{uuid.uuid4().hex[:8]}.gcode"

    def _require_ready(self, s: Session) -> None:
        if not s.objects:
            raise PrusaMcpError("La cama está vacía: añade algún modelo con add_model.")
        if not s.config_file and not (s.printer and s.print_profile and s.filaments):
            raise PrusaMcpError("Selecciona impresora, perfil de impresión y filamento (select_profiles).")

    def _source_values(self, s: Session) -> dict[str, str] | None:
        if s.config_file:
            return load_flat_file(s.config_file)
        merged: dict[str, str] = {}
        for kind, name in (("printer", s.printer), ("print", s.print_profile), ("filament", s.filaments[0] if s.filaments else None)):
            if not name:
                return None
            values = resolve_preset_values(self.install, self.datadir, kind, name)
            if values is None:
                return None
            merged.update({k: v for k, v in values.items() if classify_key(k) in (kind, None)})
        return merged

    def _printer_values(self, s: Session, source: dict[str, str] | None = None) -> dict[str, str]:
        self._require_ready(s)
        values = dict(source if source is not None else (self._source_values(s) or {}))
        values.update(s.overrides)
        if "bed_shape" not in values and s.printer:
            for p in self.list_printers():
                if p.name == s.printer:
                    values["bed_shape"] = f"0x0,{p.bed_width:g}x0,{p.bed_width:g}x{p.bed_depth:g},0x{p.bed_depth:g}"
                    values.setdefault("max_print_height", f"{p.max_height:g}")
        if "bed_shape" not in values:
            raise PrusaMcpError("No se pudo determinar el tamaño de la cama de la impresora.")
        return values

    def _check_height(self, s: Session, printer_values: dict[str, str]) -> None:
        try:
            max_h = float(printer_values.get("max_print_height", "0"))
        except ValueError:
            return
        if max_h <= 0:
            return
        for obj in s.objects:
            size_z = float(self._transformed_info(obj)[1]["size_z"])
            if size_z > max_h + 1e-6:
                raise PrusaMcpError(f"El objeto {obj.id} mide {size_z:.1f} mm de alto y la impresora admite {max_h:g} mm.")

    def _transformed_info(self, obj: PlateObject) -> tuple[Path, dict[str, str]]:
        """3MF with the object's rotation/scale applied (cached) and its --info."""
        key = f"{obj.path.resolve()}|{obj.path.stat().st_mtime}|{obj.rotate_z}|{obj.rotate_x}|{obj.rotate_y}|{obj.scale_percent}"
        h = hashlib.sha1(key.encode()).hexdigest()[:16]
        target = self._cache_dir / f"obj-{h}.3mf"
        info_file = self._cache_dir / f"obj-{h}.info"
        if not target.exists():
            args = []
            if obj.rotate_z:
                args += ["--rotate", obj.rotate_z]
            if obj.rotate_x:
                args += ["--rotate-x", obj.rotate_x]
            if obj.rotate_y:
                args += ["--rotate-y", obj.rotate_y]
            if obj.scale_percent != 100:
                args += ["--scale", f"{obj.scale_percent:g}%"]
            run_cli(self.install, [*args, "--export-3mf", "-o", target, obj.path], timeout=300)
        if not info_file.exists():
            info_file.write_text(dump_flat(self.model_info(target)), encoding="utf-8")
        return target, load_flat_file(info_file)

    def _resolve_placements(self, s: Session, printer_values: dict[str, str]) -> list[Footprint]:
        bed = parse_bed_shape(printer_values["bed_shape"])
        polygon = parse_bed_polygon(printer_values["bed_shape"])
        try:
            spacing = float(printer_values.get("duplicate_distance", DEFAULT_SPACING))
        except ValueError:
            spacing = DEFAULT_SPACING
        footprints = []
        for obj in s.objects:
            _, info = self._transformed_info(obj)
            for n, inst in enumerate(obj.instances):
                footprints.append(Footprint(obj.id, n, float(info["size_x"]), float(info["size_y"]), inst.center, inst.fixed))
        placed = pack(footprints, bed, spacing, polygon)
        problems = validate(placed, bed, spacing, polygon)
        if problems:
            raise PrusaMcpError("Problemas de colocación en la cama:\n" + "\n".join(problems))
        return placed

    def _instance_files(self, s: Session, placements: list[Footprint], job: Path) -> list[Path]:
        files = []
        for f in placements:
            src, _ = self._transformed_info(s.get(f.object_id))
            dst = job / f"inst-{f.object_id}-{f.instance}.3mf"
            run_cli(self.install, ["--center", f"{f.center[0]:.4f},{f.center[1]:.4f}", "--export-3mf", "-o", dst, src], timeout=300)
            files.append(dst)
        return files

    def _config_args(self, s: Session, job: Path) -> list:
        if s.config_file:
            args = ["--load", s.config_file]
        else:
            args = ["--datadir", self.datadir, "--printer-profile", s.printer, "--print-profile", s.print_profile,
                    "--material-profile", s.filaments[0]]
        overrides = dict(s.overrides)
        if not self.allow_post_process:
            overrides["post_process"] = ""
        ov = job / "overrides.ini"
        ov.write_text(dump_flat(overrides), encoding="utf-8")
        return [*args, "--load", ov]

    @staticmethod
    def _merge_args(inputs: list[Path]) -> list[str]:
        return ["--merge", "--dont-arrange"] if len(inputs) > 1 else ["--dont-arrange"]

    def _multi_extruder_warning(self, s: Session) -> list[str]:
        if s.config_file or not s.printer:
            return []
        values = resolve_preset_values(self.install, self.datadir, "printer", s.printer) or {}
        if len(values.get("nozzle_diameter", "").split(",")) > 1:
            return ["Perfiles multiextrusor no soportados en esta versión: se ha laminado con un solo extrusor."]
        return []

    def _probe(self, printer: str, print_profile: str, filament: str, expected: dict[str, str]) -> None:
        """Slice a tiny cube with the given presets and check PrusaSlicer really applies `expected`."""
        job = self._new_job()
        cube = job / "probe.stl"
        cube.write_text(_PROBE_CUBE, encoding="utf-8")
        out = job / "probe.gcode"
        overrides = job / "probe-overrides.ini"
        overrides.write_text("post_process = \n", encoding="utf-8")
        run_cli(self.install, ["--datadir", self.datadir, "--printer-profile", printer, "--print-profile", print_profile,
                               "--material-profile", filament, "--load", overrides, "--no-binary-gcode",
                               "--export-gcode", "-o", out, cube])
        if not out.exists():
            raise PrusaMcpError("Se guardó el perfil, pero PrusaSlicer no consigue laminar con él.")
        mismatches = compare(read_effective_config(out), expected)
        if mismatches:
            detail = "; ".join(f"{m.key}: esperado {m.expected!r}, obtenido {m.actual!r}" for m in mismatches)
            raise PrusaMcpError(f"Se guardó el perfil, pero PrusaSlicer no lo aplica como se esperaba ({detail}).")
        shutil.rmtree(job, ignore_errors=True)


def publish_file(src: Path, dst: Path) -> None:
    """Move a finished file to its final place, also across drives (temp → SD card/USB)."""
    dst = Path(dst)
    tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise PrusaMcpError(f"No se pudo guardar '{dst}': {e}. El G-code verificado sigue en '{src}'.") from e
    Path(src).unlink(missing_ok=True)
