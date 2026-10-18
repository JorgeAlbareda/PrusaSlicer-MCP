"""OctoPrint REST API client."""

from __future__ import annotations

from pathlib import Path

from prusaslicer_mcp.hosts.base import UPLOAD_TIMEOUT_S, HttpHost, PrinterStatus


class OctoPrintHost(HttpHost):
    def upload(self, path: Path, start: bool = False) -> str:
        path = Path(path)
        data = self._json(
            "POST",
            "/api/files/local",
            timeout=UPLOAD_TIMEOUT_S,
            files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
            data={"print": "true" if start else "false"},
        )
        return data.get("files", {}).get("local", {}).get("name", path.name)

    def status(self) -> PrinterStatus:
        job = self._json("GET", "/api/job")
        printer = self._json("GET", "/api/printer", ok=(200, 409))
        temps = printer.get("temperature", {})
        name = (job.get("job") or {}).get("file", {}).get("name")
        return PrinterStatus(
            state=job.get("state", "unknown"),
            progress=(job.get("progress") or {}).get("completion"),
            file=name,
            nozzle_temp=temps.get("tool0", {}).get("actual"),
            bed_temp=temps.get("bed", {}).get("actual"),
            job_id=name,
            raw={"job": job, "printer": printer},
        )

    def start(self, remote: str) -> None:
        self._request("POST", f"/api/files/local/{remote}", json={"command": "select", "print": True})

    def pause(self) -> None:
        self._request("POST", "/api/job", json={"command": "pause", "action": "pause"})

    def resume(self) -> None:
        self._request("POST", "/api/job", json={"command": "pause", "action": "resume"})

    def cancel(self) -> None:
        self._request("POST", "/api/job", json={"command": "cancel"})
