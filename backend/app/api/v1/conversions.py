import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.domain.conversions import convert_dicom_upload_to_export, convert_media_upload_to_dicom
from app.utilities import ensure_directory_exists
from app.utilities.format_converters_core import resolve_format
from app.utilities.logging_utils import log_conversion
from app.utilities.url_helpers import public_api_v1_base_url
from config.config import SUPPORTED_FORMATS

router = APIRouter(prefix="/conversions", tags=["conversions"])


def _download_base_url(request: Request) -> str:
    return public_api_v1_base_url(request)


@router.post("/dicom-export")
async def convert_dicom_to_export(
    request: Request,
    file: UploadFile = File(...),
    format: str = Form(...),
    quality: int = Query(95),
    output_dir: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await convert_dicom_upload_to_export(
        file=file,
        requested_format=format,
        output_dir=output_dir or "persistent_output/exports",
        quality=quality,
        download_base_url=_download_base_url(request),
        session=session,
    )


@router.post("/dicom-export/batch", response_model=list[dict])
async def convert_dicom_to_export_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    formats: list[str] = Form(...),
    quality: int = Form(95),
    output_dir: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        resolved_formats = [resolve_format(fmt) for fmt in formats]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if len(files) != len(resolved_formats):
        raise HTTPException(status_code=400, detail="Mismatch between files and formats.")

    invalid_formats = [fmt for fmt in resolved_formats if fmt not in SUPPORTED_FORMATS]
    if invalid_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported formats: {invalid_formats}")

    effective_output_dir = ensure_directory_exists(output_dir or "persistent_output/exports")
    results = []

    for file, requested_format in zip(files, resolved_formats):
        file_results = {
            "input_file": file.filename,
            "outputs": [],
            "metadata": {},
            "study_instance_uid": None,
        }
        try:
            converted = await convert_dicom_upload_to_export(
                file=file,
                requested_format=requested_format,
                output_dir=str(effective_output_dir),
                quality=quality,
                download_base_url=_download_base_url(request),
                session=session,
            )
            file_results["metadata"] = converted["metadata"]
            file_results["study_instance_uid"] = converted["study_instance_uid"]
            file_results["outputs"].append(
                {
                    "format": converted["format"],
                    "file_path": converted["file_path"],
                    "download_url": converted["download_url"],
                    "status": "success",
                }
            )
        except Exception as exc:
            file_results["outputs"].append(
                {
                    "format": requested_format,
                    "status": "failed",
                    "error": str(exc),
                }
            )

        results.append(file_results)

    return results


@router.post("/media-import")
async def convert_media_to_dicom(
    request: Request,
    file: UploadFile = File(...),
    input_format: str = Form(...),
    dicom_headers_json: str = Form("{}"),
    output_dir: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        headers = json.loads(dicom_headers_json) if dicom_headers_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid dicom_headers_json: {exc}") from exc

    return await convert_media_upload_to_dicom(
        file=file,
        input_format=input_format,
        headers=headers,
        work_dir=output_dir or tempfile.mkdtemp(),
        download_base_url=_download_base_url(request),
        session=session,
    )


@router.post("/media-import/batch", response_model=list[dict])
async def convert_media_to_dicom_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    input_formats: str = Query(...),
    dicom_headers: str = Form("[]"),
    output_dir: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    image_files = [file for file in files if not (file.filename and file.filename.endswith(".json"))]
    input_formats_list = [fmt.strip() for fmt in input_formats.split(",") if fmt.strip()]
    if len(image_files) != len(input_formats_list):
        raise HTTPException(status_code=400, detail="Mismatch between files and input formats.")

    try:
        parsed_headers = json.loads(dicom_headers) if dicom_headers else []
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid dicom_headers: {exc}") from exc

    metadata_by_name: dict[str, dict] = {}
    if isinstance(parsed_headers, list):
        headers_by_index = [item if isinstance(item, dict) else {} for item in parsed_headers]
    elif isinstance(parsed_headers, dict):
        headers_by_index = []
        metadata_by_name = {str(key): value for key, value in parsed_headers.items() if isinstance(value, dict)}
    else:
        headers_by_index = []

    target_output_dir = output_dir or tempfile.mkdtemp()
    os.makedirs(target_output_dir, exist_ok=True)
    results = []

    for index, (file, input_format) in enumerate(zip(image_files, input_formats_list)):
        try:
            raw_headers = metadata_by_name.get(file.filename or "", {})
            if not raw_headers and index < len(headers_by_index):
                raw_headers = headers_by_index[index]

            result = await convert_media_upload_to_dicom(
                file=file,
                input_format=input_format,
                headers=raw_headers,
                work_dir=target_output_dir,
                download_base_url=_download_base_url(request),
                session=session,
            )
            results.append(result)
        except Exception as exc:
            await log_conversion(
                session=session,
                input_file=file.filename or "",
                output_file="",
                format="dicom",
                status="failed",
                study_uid="",
                error=str(exc),
                metadata_quality="invalid",
            )
            results.append(
                {
                    "input_file": file.filename,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return results
