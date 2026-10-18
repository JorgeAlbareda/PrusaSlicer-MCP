"""Check that a G-code was produced with the configuration that was asked for.

PrusaSlicer appends the full effective configuration as `; key = value` comments between
`; prusaslicer_config = begin` and `; prusaslicer_config = end`. Matching it proves which
configuration was used; it does not prove the G-code is safe to print.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prusaslicer_mcp.errors import BinaryGcodeError, PrusaMcpError

BEGIN = "; prusaslicer_config = begin"
END = "; prusaslicer_config = end"
CHUNK = 1 << 20

CRITICAL_KEYS: tuple[str, ...] = (
    "bed_shape",
    "nozzle_diameter",
    "filament_diameter",
    "temperature",
    "first_layer_temperature",
    "bed_temperature",
    "first_layer_bed_temperature",
    "layer_height",
    "first_layer_height",
    "gcode_flavor",
    "printer_model",
    "use_relative_e_distances",
)


@dataclass
class Mismatch:
    key: str
    expected: str
    actual: str | None


@dataclass
class Verification:
    ok: bool
    checked_keys: list[str] = field(default_factory=list)
    unchecked_keys: list[str] = field(default_factory=list)
    mismatches: list[Mismatch] = field(default_factory=list)


def ensure_text_gcode(path: Path) -> None:
    with open(path, "rb") as f:
        if f.read(4) == b"GCDE":
            raise BinaryGcodeError(
                f"'{path}' es G-code binario (.bgcode). Lamina con G-code de texto para poder analizarlo."
            )


def read_effective_config(gcode: Path) -> dict[str, str]:
    ensure_text_gcode(gcode)
    with open(gcode, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        tail = b""
        while pos > 0 and BEGIN.encode() not in tail:
            step = min(CHUNK, pos)
            pos -= step
            f.seek(pos)
            tail = f.read(step) + tail
    text = tail.decode("utf-8", errors="replace")
    start = text.rfind(BEGIN)
    if start < 0:
        raise PrusaMcpError(f"'{gcode}' no contiene la configuración de PrusaSlicer al final.")
    config: dict[str, str] = {}
    for line in text[start + len(BEGIN):].splitlines():
        if line.startswith(END):
            break
        if line.startswith("; ") and " = " in line:
            key, _, value = line[2:].partition(" = ")
            config[key.strip()] = value.rstrip("\r")
        elif line.startswith("; ") and line.rstrip().endswith(" ="):
            config[line[2:].rstrip()[:-2].strip()] = ""
    return config


def _norm_atom(atom: str) -> str:
    atom = atom.strip()
    pct = atom.endswith("%")
    num = atom[:-1] if pct else atom
    try:
        value = repr(float(num))
    except ValueError:
        return atom
    return value + ("%" if pct else "")


def normalize(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return ",".join(_norm_atom(a) for a in value.split(","))


def compare(effective: dict[str, str], expected: dict[str, str]) -> list[Mismatch]:
    mismatches = []
    for key, want in expected.items():
        got = effective.get(key)
        if got is None or normalize(got) != normalize(want):
            mismatches.append(Mismatch(key, want, got))
    return mismatches


def expected_ids(printer: str, print_: str, filaments: list[str]) -> dict[str, str]:
    return {
        "printer_settings_id": printer,
        "print_settings_id": print_,
        "filament_settings_id": ";".join(filaments),
    }


def build_expected(
    ids: dict[str, str], source_values: dict[str, str] | None, overrides: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    expected = dict(ids)
    unchecked: list[str] = []
    for key in CRITICAL_KEYS:
        if source_values is not None and key in source_values:
            expected[key] = source_values[key]
        elif key not in overrides:
            unchecked.append(key)
    expected.update(overrides)
    return expected, unchecked


def verify(gcode: Path, expected: dict[str, str], unchecked: list[str]) -> Verification:
    mismatches = compare(read_effective_config(gcode), expected)
    return Verification(
        ok=not mismatches,
        checked_keys=list(expected),
        unchecked_keys=list(unchecked),
        mismatches=mismatches,
    )
