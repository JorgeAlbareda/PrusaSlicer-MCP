"""One-time confirmation codes for actions on a physical printer.

A code is bound to the action and its exact parameters (printer and current job), expires
and can be used once. This is a client-enforced confirmation: the model could replay the
code itself, which is why printer control is also disabled unless the user enables it.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from prusaslicer_mcp.errors import ConfirmationError

CODE_TTL_S = 120.0


@dataclass
class _Pending:
    action: str
    params: str
    expires: float


def _canonical(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=str)


class ConfirmationGate:
    def __init__(self, ttl_s: float = CODE_TTL_S, clock: Callable[[], float] = time.monotonic):
        self.ttl_s = ttl_s
        self._clock = clock
        self._pending: dict[str, _Pending] = {}

    def request(self, action: str, params: dict) -> str:
        now = self._clock()
        self._pending = {c: p for c, p in self._pending.items() if p.expires > now}
        code = secrets.token_urlsafe(6)[:8]
        self._pending[code] = _Pending(action, _canonical(params), now + self.ttl_s)
        return code

    def consume(self, code: str, action: str, params: dict) -> None:
        pending = self._pending.pop(code, None)
        if pending is None:
            raise ConfirmationError("Código de confirmación desconocido o ya usado. Pide uno nuevo.")
        if pending.expires <= self._clock():
            raise ConfirmationError("El código de confirmación ha caducado. Pide uno nuevo.")
        if pending.action != action or pending.params != _canonical(params):
            raise ConfirmationError(
                "El código no corresponde a esta acción, impresora o trabajo (puede que el trabajo haya cambiado). "
                "Pide uno nuevo."
            )
