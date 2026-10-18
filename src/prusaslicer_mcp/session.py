"""Plate state kept by the CLI engine: selected profiles, setting overrides and objects."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path

from prusaslicer_mcp.errors import PrusaMcpError

MODEL_EXTENSIONS = {".stl", ".3mf", ".obj", ".step", ".stp", ".amf"}


@dataclass
class Instance:
    center: tuple[float, float] | None = None
    fixed: bool = False


@dataclass
class PlateObject:
    id: int
    path: Path
    rotate_z: float = 0
    rotate_x: float = 0
    rotate_y: float = 0
    scale_percent: float = 100
    instances: list[Instance] = field(default_factory=lambda: [Instance()])
    extruder: int = 1

    def is_neutral(self) -> bool:
        return (self.rotate_z, self.rotate_x, self.rotate_y, self.scale_percent) == (0, 0, 0, 100)


@dataclass
class Session:
    printer: str | None = None
    print_profile: str | None = None
    filaments: list[str] = field(default_factory=list)
    config_file: Path | None = None
    overrides: dict[str, str] = field(default_factory=dict)
    objects: list[PlateObject] = field(default_factory=list)
    _next_id: int = 1

    def get(self, object_id: int) -> PlateObject:
        for o in self.objects:
            if o.id == object_id:
                return o
        raise PrusaMcpError(f"No hay ningún objeto con id {object_id} en la cama.")

    def add_object(self, path: Path, copies: int = 1) -> PlateObject:
        path = Path(path)
        if not path.is_file():
            raise PrusaMcpError(f"No existe el archivo '{path}'.")
        if path.suffix.lower() not in MODEL_EXTENSIONS:
            raise PrusaMcpError(
                f"Formato no soportado '{path.suffix}'. Usa uno de: {', '.join(sorted(MODEL_EXTENSIONS))}."
            )
        if copies < 1:
            raise PrusaMcpError("El número de copias debe ser al menos 1.")
        obj = PlateObject(id=self._next_id, path=path, instances=[Instance() for _ in range(copies)])
        self._next_id += 1
        self.objects.append(obj)
        return obj

    def remove_object(self, object_id: int) -> None:
        self.objects.remove(self.get(object_id))

    def clear(self) -> None:
        self.objects.clear()

    def transform(
        self,
        object_id: int,
        *,
        rotate_z: float | None = None,
        rotate_x: float | None = None,
        rotate_y: float | None = None,
        scale_percent: float | None = None,
        copies: int | None = None,
    ) -> PlateObject:
        obj = self.get(object_id)
        if scale_percent is not None and scale_percent <= 0:
            raise PrusaMcpError("La escala debe ser mayor que 0 %.")
        if copies is not None and copies < 1:
            raise PrusaMcpError("El número de copias debe ser al menos 1.")
        before = (obj.rotate_z, obj.rotate_x, obj.rotate_y, obj.scale_percent)
        if rotate_z is not None:
            obj.rotate_z = rotate_z
        if rotate_x is not None:
            obj.rotate_x = rotate_x
        if rotate_y is not None:
            obj.rotate_y = rotate_y
        if scale_percent is not None:
            obj.scale_percent = scale_percent
        if (obj.rotate_z, obj.rotate_x, obj.rotate_y, obj.scale_percent) != before:
            for inst in obj.instances:
                if not inst.fixed:
                    inst.center = None
        if copies is not None:
            if copies > len(obj.instances):
                obj.instances.extend(Instance() for _ in range(copies - len(obj.instances)))
            else:
                del obj.instances[copies:]
        return obj

    def place(self, object_id: int, instance: int, x: float, y: float) -> None:
        obj = self.get(object_id)
        if not 0 <= instance < len(obj.instances):
            raise PrusaMcpError(f"El objeto {object_id} no tiene la copia {instance}.")
        obj.instances[instance] = Instance(center=(float(x), float(y)), fixed=True)

    def unplace_all(self, include_fixed: bool = False) -> None:
        for obj in self.objects:
            for inst in obj.instances:
                if include_fixed or not inst.fixed:
                    inst.center = None
                    inst.fixed = False

    def set_setting(self, key: str, value: str) -> None:
        self.overrides[key] = str(value)

    def reset_setting(self, key: str) -> None:
        self.overrides.pop(key, None)

    def select_profiles(self, printer: str, print_profile: str, filaments: list[str]) -> None:
        self.printer, self.print_profile, self.filaments = printer, print_profile, list(filaments)
        self.config_file = None

    def snapshot(self) -> Session:
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_next_id")
        d["config_file"] = str(self.config_file) if self.config_file else None
        for o in d["objects"]:
            o["path"] = str(o["path"])
        return d
