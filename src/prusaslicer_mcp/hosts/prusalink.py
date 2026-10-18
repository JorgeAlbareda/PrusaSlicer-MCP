"""PrusaLink v1 API client."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from prusaslicer_mcp.errors import HostError
from prusaslicer_mcp.hosts.base import UPLOAD_TIMEOUT_S, HttpHost, PrinterStatus


class PrusaLinkHost(HttpHost):
    def _storage(self) -> str:
        if self.cfg.storage:
            return "/" + self.cfg.storage.strip("/")
        data = self._json("GET", "/api/v1/storage")
        for s in data.get("storage_list", []):
            if s.get("available") and not s.get("read_only"):
                return "/" + s["path"].strip("/")
        raise HostError(f"'{self.cfg.name}' no tiene ningún almacenamiento disponible para escribir.")

    def upload(self, path: Path, start: bool = False) -> str:
        path = Path(path)
        remote = f"{self._storage()}/{path.name}"
        r = self._request(
            "PUT",
            f"/api/v1/files{quote(remote)}",
            timeout=UPLOAD_TIMEOUT_S,
            ok=(200, 201, 204, 409),
            content=path.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "Print-After-Upload": "?1" if start else "?0",
                "Overwrite": "?0",
            },
        )
        if r.status_code == 409:
            raise HostError("Ya existe un archivo con ese nombre en la impresora. Renómbralo o bórralo antes.")
        return remote

    def _job(self) -> dict:
        return self._json("GET", "/api/v1/job", ok=(200, 204))

    def _job_id(self) -> str:
        job_id = self._job().get("id")
        if job_id is None:
            raise HostError(f"'{self.cfg.name}' no tiene ningún trabajo en curso.")
        return str(job_id)

    def status(self) -> PrinterStatus:
        data = self._json("GET", "/api/v1/status")
        printer = data.get("printer", {})
        job = data.get("job") or {}
        file = (self._job().get("file") or {}).get("name") if job else None
        progress = job.get("progress")
        return PrinterStatus(
            state=printer.get("state", "unknown"),
            progress=float(progress) if progress is not None else None,
            file=file,
            nozzle_temp=printer.get("temp_nozzle"),
            bed_temp=printer.get("temp_bed"),
            job_id=str(job["id"]) if job.get("id") is not None else None,
            raw=data,
        )

    def start(self, remote: str) -> None:
        self._request("POST", f"/api/v1/files{quote(remote)}")

    def pause(self) -> None:
        self._request("PUT", f"/api/v1/job/{self._job_id()}/pause")

    def resume(self) -> None:
        self._request("PUT", f"/api/v1/job/{self._job_id()}/resume")

    def cancel(self) -> None:
        self._request("DELETE", f"/api/v1/job/{self._job_id()}")
