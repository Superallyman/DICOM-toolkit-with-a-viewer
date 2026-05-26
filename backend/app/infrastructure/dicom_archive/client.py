from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from config.config import (
    DICOM_ARCHIVE_DICOMWEB_URL,
    DICOM_ARCHIVE_PASSWORD,
    DICOM_ARCHIVE_STOW_URL,
    DICOM_ARCHIVE_USERNAME,
    DICOM_ARCHIVE_ENABLED,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveStoreResult:
    enabled: bool
    stored: bool
    status_code: Optional[int] = None
    detail: str = ""


class DicomArchiveClient:
    """DICOMweb STOW-RS client for the production archive boundary."""

    def __init__(
        self,
        dicomweb_url: str = DICOM_ARCHIVE_DICOMWEB_URL,
        stow_url: str = DICOM_ARCHIVE_STOW_URL,
        username: str | None = DICOM_ARCHIVE_USERNAME,
        password: str | None = DICOM_ARCHIVE_PASSWORD,
        enabled: bool = DICOM_ARCHIVE_ENABLED,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.dicomweb_url = dicomweb_url.rstrip("/")
        self.stow_url = stow_url.rstrip("/")
        self.username = username
        self.password = password
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds

    async def status(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "reachable": False, "detail": "Archive integration disabled"}

        auth = (self.username, self.password) if self.username and self.password else None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.dicomweb_url}/studies?limit=1", auth=auth)
            return {
                "enabled": True,
                "reachable": 200 <= response.status_code < 500,
                "status_code": response.status_code,
                "dicomweb_url": self.dicomweb_url,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "reachable": False,
                "dicomweb_url": self.dicomweb_url,
                "detail": str(exc),
            }

    async def search_studies(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        patient_id: str | None = None,
        study_date: str | None = None,
        modality: str | None = None,
    ) -> list[dict]:
        if not self.enabled:
            return []

        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if patient_id:
            params["PatientID"] = patient_id
        if study_date:
            params["StudyDate"] = study_date
        if modality:
            params["Modality"] = modality

        auth = (self.username, self.password) if self.username and self.password else None
        headers = {"Accept": "application/dicom+json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.dicomweb_url}/studies",
                params=params,
                headers=headers,
                auth=auth,
            )
        response.raise_for_status()
        return response.json()

    async def store_file(self, dicom_path: str | Path) -> ArchiveStoreResult:
        if not self.enabled:
            return ArchiveStoreResult(enabled=False, stored=False, detail="Archive storage disabled")

        path = Path(dicom_path)
        if not path.is_file():
            return ArchiveStoreResult(enabled=True, stored=False, detail=f"DICOM file not found: {path}")

        boundary = "dicom-toolkit-stow"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/dicom\r\n\r\n"
        ).encode("ascii") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")

        headers = {
            "Accept": "application/dicom+json, application/json",
            "Content-Type": f'multipart/related; type="application/dicom"; boundary={boundary}',
        }
        auth = (self.username, self.password) if self.username and self.password else None

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.stow_url, content=body, headers=headers, auth=auth)
            if 200 <= response.status_code < 300:
                return ArchiveStoreResult(
                    enabled=True,
                    stored=True,
                    status_code=response.status_code,
                    detail="Stored in DICOM archive",
                )
            return ArchiveStoreResult(
                enabled=True,
                stored=False,
                status_code=response.status_code,
                detail=response.text[:500],
            )
        except Exception as exc:
            return ArchiveStoreResult(enabled=True, stored=False, detail=str(exc))


async def store_dicom_file_best_effort(dicom_path: str | Path) -> ArchiveStoreResult:
    """Store a DICOM file in the archive without failing the caller's workflow."""
    result = await DicomArchiveClient().store_file(dicom_path)
    if result.enabled and not result.stored:
        logger.warning("[ARCHIVE] Store failed for %s: %s", dicom_path, result.detail)
    elif result.stored:
        logger.info("[ARCHIVE] Stored %s", dicom_path)
    return result
