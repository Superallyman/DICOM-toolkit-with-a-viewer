from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.jobs import create_job
from app.domain.jobs.service import serialize_job
from config.config import PERSISTENT_OUTPUT_DIR


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "mime-upload"


async def stage_mime_ingest_job(
    *,
    files: list[UploadFile],
    wrap_non_dicom: bool,
    session: AsyncSession,
    output_dir: str | None = None,
    base_url: str = "/",
    priority: int = 100,
) -> dict[str, Any]:
    staging_root = Path(PERSISTENT_OUTPUT_DIR) / "uploads" / "mime"
    staging_root.mkdir(parents=True, exist_ok=True)

    job = await create_job(
        session,
        job_type="ingest.mime",
        input_payload={
            "files": [],
            "wrap_non_dicom": wrap_non_dicom,
            "output_dir": output_dir,
            "base_url": base_url,
        },
        priority=priority,
    )

    job_dir = staging_root / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)

    staged_files: list[str] = []
    for upload in files:
        filename = _safe_filename(upload.filename or "mime-upload")
        path = job_dir / filename
        path.write_bytes(await upload.read())
        staged_files.append(str(path))

    job.input_payload = {
        "files": staged_files,
        "wrap_non_dicom": wrap_non_dicom,
        "output_dir": output_dir,
        "base_url": base_url,
    }
    await session.flush()
    return serialize_job(job)
