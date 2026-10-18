"""Networked printer hosts: OctoPrint, Moonraker (Klipper) and PrusaLink."""

from __future__ import annotations

import httpx

from prusaslicer_mcp.errors import HostError
from prusaslicer_mcp.hosts.base import PrinterStatus, PrintHost
from prusaslicer_mcp.hosts.config import HostConfig, load_physical_printers
from prusaslicer_mcp.hosts.moonraker import MoonrakerHost
from prusaslicer_mcp.hosts.octoprint import OctoPrintHost
from prusaslicer_mcp.hosts.prusalink import PrusaLinkHost

_CLIENTS = {"octoprint": OctoPrintHost, "moonraker": MoonrakerHost, "prusalink": PrusaLinkHost}

__all__ = ["HostConfig", "PrinterStatus", "PrintHost", "load_physical_printers", "make_host"]


def make_host(cfg: HostConfig, transport: httpx.BaseTransport | None = None) -> PrintHost:
    cls = _CLIENTS.get(cfg.host_type)
    if cls is None:
        raise HostError(
            f"Tipo de host no soportado: {cfg.host_type}. Soportados: {', '.join(sorted(_CLIENTS))}."
        )
    return cls(cfg, transport)
