from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable

from app.db.database import async_session_factory
from app.db.models import ProcessingJob
from app.domain.conversions import convert_dicom_path_to_export, convert_media_path_to_dicom
from app.domain.jobs import claim_next_job, mark_job_failed, mark_job_succeeded
from app.domain.mime.ingestion import ingest_mime_uploads
from starlette.datastructures import UploadFile

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

JobHandler = Callable[[ProcessingJob], Awaitable[dict]]


async def _health_ping(job: ProcessingJob) -> dict:
    return {"message": "worker is alive", "input": job.input_payload}


async def _convert_dicom_to_export(job: ProcessingJob) -> dict:
    payload = job.input_payload or {}
    dicom_path = payload.get("dicom_path")
    output_format = payload.get("format")
    output_dir = payload.get("output_dir") or "/app/persistent_output/exports"
    quality = int(payload.get("quality") or 95)
    download_base_url = payload.get("download_base_url") or "/v1"

    if not dicom_path or not output_format:
        raise ValueError("dicom_path and format are required")

    async with async_session_factory() as session:
        result = await convert_dicom_path_to_export(
            dicom_path=dicom_path,
            requested_format=output_format,
            output_dir=output_dir,
            quality=quality,
            download_base_url=download_base_url,
            session=session,
        )
        await session.commit()
        return result


async def _convert_media_to_dicom(job: ProcessingJob) -> dict:
    payload = job.input_payload or {}
    input_path = payload.get("input_path")
    input_format = payload.get("input_format")
    headers = payload.get("dicom_headers") or {}
    work_dir = payload.get("work_dir") or "/app/persistent_output/import_work"
    download_base_url = payload.get("download_base_url") or "/v1"

    if not input_path or not input_format:
        raise ValueError("input_path and input_format are required")
    if not isinstance(headers, dict):
        raise ValueError("dicom_headers must be an object")

    async with async_session_factory() as session:
        result = await convert_media_path_to_dicom(
            input_path=input_path,
            input_format=input_format,
            headers=headers,
            work_dir=work_dir,
            download_base_url=download_base_url,
            session=session,
        )
        await session.commit()
        return result


class _WorkerRequest:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url


async def _ingest_mime(job: ProcessingJob) -> dict:
    payload = job.input_payload or {}
    file_paths = payload.get("files") or []
    wrap_non_dicom = bool(payload.get("wrap_non_dicom"))
    output_dir = payload.get("output_dir")
    base_url = payload.get("base_url") or "/"

    if not isinstance(file_paths, list) or not file_paths:
        raise ValueError("files must be a non-empty list of staged file paths")

    opened_files = []
    uploads = []
    try:
        for file_path in file_paths:
            file_obj = open(file_path, "rb")
            opened_files.append(file_obj)
            uploads.append(UploadFile(file=file_obj, filename=str(file_path).split("/")[-1].split("\\")[-1]))

        async with async_session_factory() as session:
            result = await ingest_mime_uploads(
                request=_WorkerRequest(base_url),
                files=uploads,
                session=session,
                output_dir=output_dir,
                wrap_non_dicom=wrap_non_dicom,
            )
            await session.commit()
            return result
    finally:
        for file_obj in opened_files:
            file_obj.close()


HANDLERS: dict[str, JobHandler] = {
    "health.ping": _health_ping,
    "conversion.dicom_to_export": _convert_dicom_to_export,
    "conversion.media_to_dicom": _convert_media_to_dicom,
    "ingest.mime": _ingest_mime,
}


async def process_one_job() -> bool:
    async with async_session_factory() as session:
        job = await claim_next_job(session)
        if job is None:
            await session.commit()
            return False

        handler = HANDLERS.get(job.job_type)
        if handler is None:
            await mark_job_failed(session, job, f"No handler registered for job type: {job.job_type}")
            await session.commit()
            logger.warning("No handler registered for job %s (%s)", job.id, job.job_type)
            return True

        try:
            result = await handler(job)
            await mark_job_succeeded(session, job, result)
            await session.commit()
            logger.info("Completed job %s (%s)", job.id, job.job_type)
            return True
        except Exception as exc:
            await mark_job_failed(session, job, str(exc))
            await session.commit()
            logger.exception("Failed job %s (%s)", job.id, job.job_type)
            return True


async def run_forever() -> None:
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    logger.info("Starting DICOM Toolkit worker")
    while True:
        processed = await process_one_job()
        if not processed:
            await asyncio.sleep(poll_seconds)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
