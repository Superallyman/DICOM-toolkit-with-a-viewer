from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pydicom
from fastapi import HTTPException, UploadFile
from pydicom.uid import generate_uid
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.dicom_archive import store_dicom_file_best_effort
from app.utilities import ensure_directory_exists, extract_metadata, generate_study_instance_uid
from app.utilities.endpoint_helpers import log_dicom_metadata
from app.utilities.logging_utils import log_conversion
from app.utilities.utilities import save_dicom_metadata

try:
    from dicomAnonymizer.simpledicomanonymizer import anonymize_dicom_file
except Exception:
    from app.utilities.anon_utils import anonymize_dicom_file

logger = logging.getLogger(__name__)


async def anonymize_dicom_upload(
    *,
    file: UploadFile,
    delete_private_tags: bool,
    rules_json: str | None,
    output_dir: str,
    download_base_url: str,
    session: AsyncSession,
) -> dict[str, Any]:
    src_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dcm") as src_tmp:
            src_path = src_tmp.name
            src_tmp.write(await file.read())

        try:
            pre_ds = pydicom.dcmread(src_path, stop_before_pixels=True, force=True)
            study_uid_pre = await _log_metadata_phase(session, pre_ds, phase="pre")
        except Exception as exc:
            logger.warning("[DEID] Could not read/log original DICOM: %s", exc)
            study_uid_pre = generate_study_instance_uid()

        target_dir = ensure_directory_exists(output_dir)
        dst_path = Path(target_dir) / f"anon_{Path(file.filename or 'input.dcm').stem}_{uuid.uuid4().hex}.dcm"

        extra_rules = _parse_rules(rules_json)
        anonymize_dicom_file(
            in_file=src_path,
            out_file=str(dst_path),
            extra_anonymization_rules=extra_rules,
            delete_private_tags=delete_private_tags,
        )

        ds_post = pydicom.dcmread(str(dst_path), force=True)
        metadata = extract_metadata(ds_post)
        study_uid_final = str(getattr(ds_post, "StudyInstanceUID", study_uid_pre)) or study_uid_pre

        await _log_metadata_phase(session, ds_post, phase="post")
        await store_dicom_file_best_effort(dst_path)

        try:
            conversion_id = await log_conversion(
                session=session,
                input_file=file.filename or "",
                output_file=str(dst_path),
                format="dicom",
                status="success",
                study_uid=study_uid_final,
                error="",
            )
        except Exception as exc:
            logger.warning("[DEID] Failed to write anonymization conversion log: %s", exc)
            conversion_id = None

        return {
            "status": "success",
            "download_url": _download_url(download_base_url, conversion_id, dst_path),
            "conversion_id": conversion_id,
            "output_file": str(dst_path),
            "metadata": metadata,
            "study_instance_uid": study_uid_final,
            "anonymized": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[DEID] Anonymization failed")
        try:
            await log_conversion(
                session=session,
                input_file=(file.filename if file else ""),
                output_file="",
                format="dicom",
                status="failed",
                study_uid="",
                error=str(exc),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Anonymization failed: {exc}") from exc
    finally:
        if src_path and os.path.exists(src_path):
            try:
                os.unlink(src_path)
            except Exception:
                pass


def _parse_rules(rules_json: str | None) -> dict[str, Any] | None:
    if not rules_json:
        return None
    try:
        return json.loads(rules_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid rules_json: {exc}") from exc


def _download_url(download_base_url: str, conversion_id: int | None, output_path: Path) -> str:
    base_url = download_base_url.rstrip("/")
    if conversion_id is not None:
        return f"{base_url}/files/{conversion_id}/download"
    return f"{base_url}/files/download?file_path={output_path}"


async def _log_metadata_phase(session: AsyncSession, ds: pydicom.dataset.FileDataset, phase: str) -> str:
    study_uid = str(getattr(ds, "StudyInstanceUID", generate_study_instance_uid()))
    series_uid = str(getattr(ds, "SeriesInstanceUID", generate_uid()))
    sop_uid = str(getattr(ds, "SOPInstanceUID", generate_uid()))

    try:
        await log_dicom_metadata(
            session,
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            ds=ds,
            phase=phase,
        )
        await session.commit()
    except SQLAlchemyError as exc:
        logger.error("[DEID] DB commit failed while saving %s metadata: %s", phase, exc)
        await session.rollback()
    except Exception as exc:
        logger.warning("[DEID] Structured metadata logging failed; using fallback: %s", exc)
        await session.rollback()
        headers_for_log = {
            "StudyInstanceUID": study_uid,
            "SeriesInstanceUID": series_uid,
            "SOPInstanceUID": sop_uid,
            "__phase": phase,
        }
        try:
            await save_dicom_metadata(headers_for_log, session)
            await session.commit()
        except Exception:
            await session.rollback()

    return study_uid
