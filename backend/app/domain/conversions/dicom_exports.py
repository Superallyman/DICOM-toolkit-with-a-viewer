from __future__ import annotations

from pathlib import Path
from typing import Any

import pydicom
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.utilities import ensure_directory_exists, extract_metadata, generate_study_instance_uid
from app.utilities.format_converters_core import dicom_to_format, resolve_format
from app.utilities.logging_utils import log_conversion


async def convert_dicom_upload_to_export(
    *,
    file: UploadFile,
    requested_format: str,
    output_dir: str,
    quality: int,
    download_base_url: str,
    session: AsyncSession,
) -> dict[str, Any]:
    try:
        resolved_format = resolve_format(requested_format)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {requested_format}")

    output_directory = ensure_directory_exists(output_dir)

    try:
        file.file.seek(0)
        ds = pydicom.dcmread(file.file, force=True)
        file.file.seek(0)
        metadata = extract_metadata(ds)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to extract metadata.")

    try:
        file.file.seek(0)
        output_path = dicom_to_format(file, output_directory, resolved_format, quality)
        study_instance_uid = str(getattr(ds, "StudyInstanceUID", "") or generate_study_instance_uid())

        conversion_id = await log_conversion(
            session=session,
            input_file=file.filename or "",
            output_file=output_path,
            format=resolved_format,
            status="success",
            study_uid=study_instance_uid,
            error="",
        )

        return {
            "input_file": file.filename,
            "format": resolved_format,
            "file_path": output_path,
            "output_directory": str(output_directory),
            "download_url": _download_url(download_base_url, conversion_id, output_path),
            "conversion_id": conversion_id,
            "study_instance_uid": study_instance_uid,
            "metadata": metadata,
            "status": "success",
            "message": f"Conversion of {file.filename} to {resolved_format.upper()} successful.",
        }
    except HTTPException as exc:
        await _log_failed_conversion(session, file.filename or "", resolved_format, str(exc))
        raise
    except Exception as exc:
        await _log_failed_conversion(session, file.filename or "", resolved_format, str(exc))
        raise HTTPException(status_code=500, detail="Unexpected error during conversion.")


async def convert_dicom_path_to_export(
    *,
    dicom_path: str | Path,
    requested_format: str,
    output_dir: str,
    quality: int,
    download_base_url: str,
    session: AsyncSession,
) -> dict[str, Any]:
    path = Path(dicom_path)
    with path.open("rb") as file_obj:
        upload = StarletteUploadFile(file=file_obj, filename=path.name)
        return await convert_dicom_upload_to_export(
            file=upload,
            requested_format=requested_format,
            output_dir=output_dir,
            quality=quality,
            download_base_url=download_base_url,
            session=session,
        )


async def _log_failed_conversion(
    session: AsyncSession,
    input_file: str,
    output_format: str,
    error: str,
) -> None:
    await log_conversion(
        session=session,
        input_file=input_file,
        output_file="",
        format=output_format,
        status="failed",
        study_uid="",
        error=error,
    )


def _download_url(download_base_url: str, conversion_id: int | None, output_path: str) -> str:
    base_url = download_base_url.rstrip("/")
    if conversion_id is not None:
        return f"{base_url}/files/{conversion_id}/download"
    return f"{base_url}/files/download?file_path={output_path}"
