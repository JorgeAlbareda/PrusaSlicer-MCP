"""Common pieces of the printer host clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from prusaslicer_mcp.errors import HostError
from prusaslicer_mcp.hosts.config import HostConfig

TIMEOUT_S = 10.0
UPLOAD_TIMEOUT_S = 300.0


@dataclass
class PrinterStatus:
    state: str
    progress: float | None
    file: str | None
    nozzle_temp: float | None
    bed_temp: float | None
    job_id: str | None
    raw: dict = field(default_factory=dict)


class PrintHost(Protocol):
    def upload(self, path: Path, start: bool = False) -> str: ...
    def status(self) -> PrinterStatus: ...
    def start(self, remote: str) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def cancel(self) -> None: ...


class HttpHost:
    """Shared HTTP plumbing: auth, timeouts and error translation."""

    def __init__(self, cfg: HostConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self._transport = transport

    def _client(self, timeout: float = TIMEOUT_S) -> httpx.Client:
        headers = {}
        auth = None
        if self.cfg.auth == "user" and self.cfg.user:
            auth = httpx.DigestAuth(self.cfg.user, self.cfg.password or "")
        elif self.cfg.api_key:
            headers["X-Api-Key"] = self.cfg.api_key
        return httpx.Client(
            base_url=self.cfg.url,
            headers=headers,
            auth=auth,
            timeout=timeout,
            transport=self._transport,
            verify=self.cfg.cafile or True,
        )

    def _request(self, method: str, path: str, *, timeout: float = TIMEOUT_S, ok=(200, 201, 204), **kw) -> httpx.Response:
        try:
            with self._client(timeout) as c:
                r = c.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise HostError(f"No se pudo conectar con '{self.cfg.name}' ({self.cfg.url}): {e}") from e
        if r.status_code in (401, 403):
            raise HostError(f"'{self.cfg.name}' rechazó las credenciales (HTTP {r.status_code}). Revisa la API key o el usuario.")
        if r.status_code not in ok:
            raise HostError(f"'{self.cfg.name}' respondió HTTP {r.status_code} a {method} {path}: {r.text[:300]}")
        return r

    def _json(self, method: str, path: str, **kw) -> dict:
        r = self._request(method, path, **kw)
        try:
            return r.json() if r.content else {}
        except ValueError:
            return {}
