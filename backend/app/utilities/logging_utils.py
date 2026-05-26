# app/utilities/logging_utils.py
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import async_session_factory
from app.db.models import ConversionLog, EventLog

# Support both metadata model shapes used across deployed databases.
try:
    # Newer model (Text metadata_json + phase column)
    from app.db.models import DicomMetadataLog  # type: ignore
except Exception:  # pragma: no cover
    DicomMetadataLog = None  # type: ignore

try:
    # Compatibility model (JSON metadata_json, no phase)
    from app.db.models import DICOMMetadataLog  # type: ignore
except Exception:  # pragma: no cover
    DICOMMetadataLog = None  # type: ignore

log = logging.getLogger(__name__)


async def log_conversion(
    session: Optional[AsyncSession] = None,
    input_file: str = "",
    output_file: str = "",
    format: str = "",
    status: str = "",
    study_uid: str = "",
    error: str = "",
    dicom_metadata: Optional[dict] = None,
    metadata_quality: Optional[str] = None,
):
    """
    Logs conversion activity to both conversion_logs and event_logs tables.

    NOTE: This keeps your existing behavior (create/commit inside here if no
    session is provided, and use the supplied session otherwise).
    """
    timestamp = datetime.utcnow()
    created_session = False

    if session is None:
        session = async_session_factory()
        created_session = True

    try:
        log_entry = ConversionLog(
            input_file=input_file,
            output_file=output_file,
            format=format,
            status=status,
            study_uid=study_uid,
            error=error,
            timestamp=timestamp,
            dicom_metadata=dicom_metadata,
            metadata_quality=metadata_quality,
        )

        event_message = (
            f"{status.upper()}: Converted {input_file} to {format.upper()}"
            if status == "success"
            else f"{status.upper()}: Failed to convert {input_file} to {format.upper()} | Error: {error}"
        )

        event_entry = EventLog(
            event_type="conversion",
            message=event_message,
            success=(status == "success"),
            timestamp=timestamp,
        )

        # Keep existing pattern: wrap the provided/created session in a context
        async with session as db:
            db.add(log_entry)
            db.add(event_entry)
            await db.commit()
            await db.refresh(log_entry)
            return log_entry.id

    except Exception:
        # Keep existing rollback behavior
        await session.rollback()
        return None
        raise
    finally:
        if created_session:
            await session.close()


async def log_event(event_type: str, payload: dict):
    """
    Logs a general event to the event_logs table.
    """
    timestamp = datetime.utcnow()
    async with async_session_factory() as session:
        try:
            log_entry = EventLog(
                event_type=event_type,
                message=str(payload),
                success=True,
                timestamp=timestamp,
            )
            session.add(log_entry)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_conversion_stats():
    """
    Retrieves conversion statistics.
    """
    async with async_session_factory() as session:
        success = await session.scalar(
            select(func.count()).where(ConversionLog.status == "success")
        )
        failure = await session.scalar(
            select(func.count()).where(ConversionLog.status == "failed")
        )
        return {"success": success, "failed": failure}


# ----------------------- NEW: save_dicom_metadata ----------------------------

async def save_dicom_metadata(
    headers: Dict[str, Any],
    session: AsyncSession,
    *,
    phase: str = "post",
) -> None:
    """
    Persist minimal identifiers (Study/Series/SOP) into dicom_metadata_logs so
    /v1/ai/deid/audit has something to read.

    IMPORTANT: This function **does not commit**. Your calling code already does
    `await session.commit()` (matching your current pattern).

    Supports both model variants:
      - New:  DicomMetadataLog (Text metadata_json + phase)
      - Compatibility: DICOMMetadataLog (JSON metadata_json, no phase)
    """
    study_uid = str(
        headers.get("StudyInstanceUID")
        or headers.get("StudyUID")
        or headers.get("study_uid")
        or ""
    )
    series_uid = str(headers.get("SeriesInstanceUID") or headers.get("series_uid") or "")
    sop_uid = str(headers.get("SOPInstanceUID") or headers.get("sop_uid") or "")

    if not study_uid:
        log.debug("[DB] save_dicom_metadata skipped (no StudyInstanceUID provided)")
        return

    payload = {
        "type": "uid_header_stub",
        "uids": {
            "StudyInstanceUID": study_uid,
            "SeriesInstanceUID": series_uid,
            "SOPInstanceUID": sop_uid,
        },
        "phase": phase,
    }

    # Prefer the newer model if available
    if DicomMetadataLog is not None:
        try:
            session.add(
                DicomMetadataLog(
                    study_uid=study_uid,
                    series_uid=series_uid or "",
                    sop_uid=sop_uid or "",
                    phase=phase,
                    metadata_json=json.dumps(payload),  # Text column on new model
                )
            )
            # No commit here; caller commits
            log.info("[DB] (new) queued dicom_metadata_logs row for study=%s phase=%s", study_uid, phase)
            return
        except SQLAlchemyError as e:
            log.warning("[DB] DicomMetadataLog insert failed: %s; will try compatibility model", e)

    # Fallback to the compatibility model shape.
    if DICOMMetadataLog is not None:
        try:
            session.add(
                DICOMMetadataLog(
                    study_uid=study_uid,
                    series_uid=series_uid or "",
                    sop_uid=sop_uid or "",
                    metadata_json=payload,  # JSON column on compatibility model
                )
            )
            log.info("[DB] (compatibility) queued dicom_metadata_logs row for study=%s", study_uid)
            return
        except SQLAlchemyError as e:
            log.error("[DB] Compatibility DICOMMetadataLog insert failed: %s", e)

    if DicomMetadataLog is None and DICOMMetadataLog is None:
        log.debug("[DB] No dicom metadata log model available; skipping write")
