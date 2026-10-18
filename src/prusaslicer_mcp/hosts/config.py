"""Physical printers configured in PrusaSlicer (datadir/physical_printer/*.ini)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from prusaslicer_mcp.ini import parse_flat


@dataclass
class HostConfig:
    name: str
    host_type: str
    url: str
    api_key: str | None
    user: str | None
    password: str | None
    auth: Literal["key", "user"]
    cafile: str | None
    storage: str | None = None

    def public(self) -> dict:
        """Description without secrets."""
        return {"name": self.name, "host_type": self.host_type, "url": self.url, "auth": self.auth}


def _url(host: str) -> str:
    host = host.strip()
    return host if "://" in host else f"http://{host}"


def load_physical_printers(datadir: Path) -> list[HostConfig]:
    folder = Path(datadir) / "physical_printer"
    if not folder.is_dir():
        return []
    hosts = []
    for f in sorted(folder.glob("*.ini")):
        v = parse_flat(f.read_text(encoding="utf-8"))
        if not v.get("print_host"):
            continue
        hosts.append(
            HostConfig(
                name=f.stem,
                host_type=v.get("host_type", "octoprint"),
                url=_url(v["print_host"]),
                api_key=v.get("printhost_apikey") or None,
                user=v.get("printhost_user") or None,
                password=v.get("printhost_password") or None,
                auth="user" if v.get("printhost_authorization_type") == "user" else "key",
                cafile=v.get("printhost_cafile") or None,
            )
        )
    return hosts
