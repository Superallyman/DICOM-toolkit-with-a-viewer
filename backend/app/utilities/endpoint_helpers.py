# app/endpoint_helpers.py
import re
import json
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
import pydicom

# Import what we may have; if a model is missing, helpers degrade gracefully.
try:
    # has input_file, output_file, study_uid
    from app.db.models import ConversionLog  # type: ignore
except Exception:  # pragma: no cover
    ConversionLog = None  # type: ignore

try:
    # JSON metadata store used by the audit endpoint
    from app.db.models import DICOMMetadataLog  # type: ignore
except Exception:  # pragma: no cover
    DICOMMetadataLog = None  # type: ignore


# -- Strategy 1: pull Study UID right out of the message ----------------------
UID_MSG_RE = re.compile(r"(?:Study(?:Instance)?UID|StudyUID)\s*[:=]\s*([0-9.]+)", re.I)


def infer_study_uid_from_message(msg: str | None) -> Optional[str]:
    if not msg:
        return None
    m = UID_MSG_RE.search(msg)
    return m.group(1) if m else None


# -- Small helper: extract a plausible filename from the message --------------
FNAME_RE = re.compile(
    r"(?:Converted|Wrote|Saved|Output(?:\s*file)?\:?)\s+([^\s\"']+\.(?:dcm|png|jpe?g|tiff?|pdf|mp4))",
    re.I,
)
ANY_FNAME_RE = re.compile(r"([A-Za-z0-9._\-/\\]+?\.(?:dcm|png|jpe?g|tiff?|pdf|mp4))", re.I)


def extract_candidate_filename(msg: str | None) -> Optional[str]:
    if not msg:
        return None
    m = FNAME_RE.search(msg)
    if not m:
        m = ANY_FNAME_RE.search(msg)
    if not m:
        return None
    # only keep the basename for matching
    fname = m.group(1)
    return fname.split("/")[-1].split("\\")[-1]


# -- Strategy 2: look up Study UID via recent conversion/metadata -------------
async def lookup_study_uid_from_metadata(
    session: AsyncSession, msg: str | None
) -> Optional[str]:
    """
    Try to find a Study UID by matching a filename mentioned in the event
    message against ConversionLog / DICOMMetadataLog.
    """
    fname = extract_candidate_filename(msg)
    if not fname:
        return None

    # Prefer ConversionLog if present
    if ConversionLog is not None:
        try:
            q = (
                select(ConversionLog.study_uid)
                .where(
                    or_(
                        ConversionLog.input_file.ilike(f"%{fname}%"),
                        ConversionLog.output_file.ilike(f"%{fname}%"),
                    )
                )
                .order_by(ConversionLog.id.desc())
                .limit(1)
            )
            r = await session.execute(q)
            suid = r.scalar_one_or_none()
            if suid:
                return str(suid)
        except Exception:
            # no hard failure — fall through to metadata table
            pass

    # Fall back to DICOMMetadataLog, if present
    if DICOMMetadataLog is not None:
        # Probe a few plausible filename columns if they exist on your model
        for colname in ("original_filename", "new_filename", "message", "source_file"):
            try:
                col = getattr(DICOMMetadataLog, colname)
            except Exception:
                continue
            try:
                q = (
                    select(DICOMMetadataLog.study_uid)
                    .where(col.ilike(f"%{fname}%"))
                    .order_by(DICOMMetadataLog.created_at.desc())
                    .limit(1)
                )
                r = await session.execute(q)
                suid = r.scalar_one_or_none()
                if suid:
                    return str(suid)
            except Exception:
                continue

    return None


# --- Minimal tag extraction for the audit ------------------------------------
SCAN_TAGS = {
    "00081030",  # StudyDescription
    "0008103E",  # SeriesDescription
    "00181030",  # ProtocolName
    "001021B0",  # AdditionalPatientHistory
    "00104000",  # PatientComments
    "00321060",  # RequestedProcedureDescription
    "00400007",  # ScheduledProcedureStepDescription
}


def extract_metadata_tags(ds: "pydicom.Dataset") -> dict:
    def get(tag_hex: str):
        try:
            g = int(tag_hex[:4], 16)
            e = int(tag_hex[4:], 16)
            v = ds.get((g, e))
            if v is None:
                return None
            # Value -> JSON-safe
            if isinstance(v.value, (list, tuple)):
                return [str(x) for x in v.value]
            return str(v.value)
        except Exception:
            return None

    out: dict = {}
    for t in SCAN_TAGS:
        val = get(t)
        if val not in (None, "", []):
            out[t] = val
    return out


# (Kept for future use; not required by the current audit, but harmless)
TEXT_TAG_VRS = {
    "AE",
    "AS",
    "CS",
    "DA",
    "DS",
    "DT",
    "IS",
    "LO",
    "LT",
    "OB",
    "OD",
    "OF",
    "OW",
    "PN",
    "SH",
    "ST",
    "TM",
    "UC",
    "UI",
    "UL",
    "UR",
    "US",
    "UT",
}


def _extract_textish(ds: "pydicom.Dataset") -> dict:
    out: dict = {}
    for elem in ds.iterall():
        try:
            vr = getattr(elem, "VR", None)
            if vr in TEXT_TAG_VRS:
                out[str(elem.tag)] = str(elem.value)
        except Exception:
            continue
    return out


# --- Unified metadata logger (backward compatible) ---------------------------
async def log_dicom_metadata(
    session: AsyncSession,
    *,
    study_uid: str,
    series_uid: str | None = None,
    sop_uid: str | None = None,
    ds: "pydicom.Dataset",
    phase: str = "post",
) -> None:
    """
    Persist a subset of header fields for De-ID audits.
    - Stores a simple dict of tag->value in `metadata_json` (what the audit expects).
    - Supports the new `phase` column ("pre" or "post") for comparison.
    """
    if DICOMMetadataLog is None:
        # Model not available; no-op to avoid breaking callers
        return

    tags = extract_metadata_tags(ds)

    row = DICOMMetadataLog(
        study_uid=study_uid,
        series_uid=series_uid or "",
        sop_uid=sop_uid or "",
        metadata_json=tags,  # JSON column with tag->value
        phase=phase,
    )
    session.add(row)
