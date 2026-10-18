"""PrusaSlicer .ini files: flat configs and config bundles (with [kind:name] sections)."""

from __future__ import annotations

import re
from pathlib import Path

from prusaslicer_mcp.errors import BundleIniError

_SECTION_RE = re.compile(r"^\[([^\]]*)\]\s*$")


def _iter_pairs(lines):
    for raw in lines:
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if _SECTION_RE.match(stripped):
            yield ("section", stripped[1:-1], None)
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        yield ("pair", key.strip(), value.strip())


def parse_flat(text: str) -> dict[str, str]:
    return {k: v for kind, k, v in _iter_pairs(text.splitlines()) if kind == "pair"}


def is_bundle(text: str) -> bool:
    return any(kind == "section" for kind, _, _ in _iter_pairs(text.splitlines()))


def parse_bundle(text: str) -> dict[str, dict[str, dict[str, str]]]:
    """Return {kind: {preset_name: {key: value}}}; "[presets]" becomes {"presets": {"": {...}}}."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    current: dict[str, str] | None = None
    for kind, key, value in _iter_pairs(text.splitlines()):
        if kind == "section":
            section_kind, _, name = key.partition(":")
            current = result.setdefault(section_kind.strip(), {}).setdefault(name.strip(), {})
        elif current is not None:
            current[key] = value
    return result


def dump_flat(values: dict[str, str]) -> str:
    return "".join(f"{k} = {v}\n" for k, v in values.items())


def load_flat_file(path: Path) -> dict[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    if is_bundle(text):
        raise BundleIniError(
            f"'{path}' es un bundle de PrusaSlicer (tiene secciones [print:…], [printer:…]…). "
            "PrusaSlicer lo ignora en silencio con --load y laminaría con valores por defecto. "
            "Impórtalo como perfiles de usuario con la herramienta import_profile_bundle."
        )
    return parse_flat(text)
