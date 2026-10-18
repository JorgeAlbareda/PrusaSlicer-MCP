"""Moonraker (Klipper) HTTP API client."""

from __future__ import annotations

from pathlib import Path

from prusaslicer_mcp.hosts.base import UPLOAD_TIMEOUT_S, HttpHost, PrinterStatus


def _result(data: dict) -> dict:
    return data.get("result", data) if isinstance(data, dict) else {}


class MoonrakerHost(HttpHost):
    def upload(self, path: Path, start: bool = False) -> str:
        path = Path(path)
        data = _result(
            self._json(
                "POST",
                "/server/files/upload",
                timeout=UPLOAD_TIMEOUT_S,
                files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
                data={"print": "true" if start else "false"},
            )
        )
        return (data.get("item") or {}).get("path", path.name)

    def status(self) -> PrinterStatus:
        data = _result(self._json("GET", "/printer/objects/query?print_stats&virtual_sdcard&extruder&heater_bed"))
        st = data.get("status", {})
        stats = st.get("print_stats", {})
        progress = st.get("virtual_sdcard", {}).get("progress")
        filename = stats.get("filename") or None
        return PrinterStatus(
            state=stats.get("state", "unknown"),
            progress=round(progress * 100, 2) if progress is not None else None,
            file=filename,
            nozzle_temp=st.get("extruder", {}).get("temperature"),
            bed_temp=st.get("heater_bed", {}).get("temperature"),
            job_id=filename,
            raw=data,
        )

    def start(self, remote: str) -> None:
        self._request("POST", "/printer/print/start", params={"filename": remote})

    def pause(self) -> None:
        self._request("POST", "/printer/print/pause")

    def resume(self) -> None:
        self._request("POST", "/printer/print/resume")

    def cancel(self) -> None:
        self._request("POST", "/printer/print/cancel")
