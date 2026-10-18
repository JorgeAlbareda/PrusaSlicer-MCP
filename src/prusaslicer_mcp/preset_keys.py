"""Which preset kind (print / filament / printer) each PrusaSlicer config key belongs to.

The table is generated from the PrusaSlicer sources by scripts/gen_preset_keys.py.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

Kind = Literal["print", "filament", "printer"]

KEY_KIND: dict[str, Kind] = json.loads(
    resources.files("prusaslicer_mcp").joinpath("data/preset_keys.json").read_text(encoding="utf-8")
)


def classify_key(key: str) -> Kind | None:
    return KEY_KIND.get(key)
