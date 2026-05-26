from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pydicom
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.dicom_archive import store_dicom_file_best_effort
from app.utilities.file_util import copy_dicom_to_ohif, hash_uid
from app.utilities.format_converters_core import convert_image_to_dicom, convert_pdf_to_dicom, convert_video_to_dicom
from app.utilities.logging_utils import log_conversion
from app.utilities.metadata import populate_required_dicom_tags, validate_metadata
from app.utilities.thumbnail_dao import generate_thumbnail
from app.utilities.endpoint_helpers import log_dicom_metadata
from config.config import OHIF_VIEWER_DIR, PERSISTENT_OUTPUT_DIR


CONVERTERS = {
    "jpeg": convert_image_to_dicom,
    "jpg": convert_image_to_dicom,
    "png": convert_image_to_dicom,
    "tiff": convert_image_to_dicom,
    "pdf": convert_pdf_to_dicom,
    "mp4": convert_video_to_dicom,
}


async def convert_media_upload_to_dicom(
    *,
    file: UploadFile,
    input_format: str,
    headers: dict[str, Any],
    work_dir: str | Path,
    download_base_url: str,
    session: AsyncSession,
) -> dict[str, Any]:
    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)
    input_path = work_path / (file.filename or "upload")

    with input_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return await convert_media_path_to_dicom(
        input_path=input_path,
        input_format=input_format,
        headers=headers,
        work_dir=work_path,
        download_base_url=download_base_url,
        session=session,
    )


async def convert_media_path_to_dicom(
    *,
    input_path: str | Path,
    input_format: str,
    headers: dict[str, Any],
    work_dir: str | Path,
    download_base_url: str,
    session: AsyncSession,
) -> dict[str, Any]:
    input_path = Path(input_path)
    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)

    normalized_format = input_format.lower()
    convert_func = CONVERTERS.get(normalized_format)
    if not convert_func:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {input_format}")

    dicom_headers = populate_required_dicom_tags(headers, input_path.name)
    dicom_headers.setdefault("SOPClassUID", "1.2.840.10008.5.1.4.1.1.7")

    study_uid = dicom_headers["StudyInstanceUID"]
    series_uid = dicom_headers["SeriesInstanceUID"]
    sop_uid = dicom_headers["SOPInstanceUID"]
    missing = validate_metadata(dicom_headers)
    metadata_quality = "incomplete" if missing else "complete"

    temp_output_dicom = work_path / f"{input_path.stem}.dcm"
    convert_func(str(input_path), str(temp_output_dicom), dicom_headers)
    if not temp_output_dicom.is_file():
        raise FileNotFoundError(f"Temp DICOM file missing: {temp_output_dicom}")

    persistent_path = (
        Path(PERSISTENT_OUTPUT_DIR)
        / "studies"
        / hash_uid(study_uid)
        / hash_uid(series_uid)
        / f"{hash_uid(sop_uid)}.dcm"
    )
    persistent_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(temp_output_dicom, persistent_path)

    ds = pydicom.dcmread(str(persistent_path), stop_before_pixels=True, force=True)
    await _log_pre_metadata(session, ds, study_uid, series_uid, sop_uid)

    try:
        thumb_path = persistent_path.with_name(f"{persistent_path.stem}_thumb.jpg")
        await generate_thumbnail(ds, thumb_path, study_uid, series_uid, sop_uid, session)
    except Exception:
        pass

    try:
        copy_dicom_to_ohif(str(persistent_path), OHIF_VIEWER_DIR)
    except Exception:
        pass

    await store_dicom_file_best_effort(persistent_path)

    conversion_id = await log_conversion(
        session=session,
        input_file=input_path.name,
        output_file=str(persistent_path),
        format="dicom",
        status="success",
        study_uid=study_uid,
        error="",
        metadata_quality=metadata_quality,
    )

    return {
        "input_file": input_path.name,
        "output_file": str(persistent_path),
        "download_url": _download_url(download_base_url, conversion_id, persistent_path),
        "conversion_id": conversion_id,
        "dicom_headers": dicom_headers,
        "status": "success",
        "missing_headers": missing,
        "study_uid": study_uid,
        "series_uid": series_uid,
        "sop_uid": sop_uid,
    }


async def _log_pre_metadata(
    session: AsyncSession,
    ds: pydicom.Dataset,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
) -> None:
    await log_dicom_metadata(
        session,
        study_uid=str(getattr(ds, "StudyInstanceUID", study_uid)),
        series_uid=str(getattr(ds, "SeriesInstanceUID", series_uid)),
        sop_uid=str(getattr(ds, "SOPInstanceUID", sop_uid)),
        ds=ds,
        phase="pre",
    )


def _download_url(download_base_url: str, conversion_id: int | None, output_path: Path) -> str:
    base_url = download_base_url.rstrip("/")
    if conversion_id is not None:
        return f"{base_url}/files/{conversion_id}/download"
    return f"{base_url}/files/download?file_path={output_path}"
