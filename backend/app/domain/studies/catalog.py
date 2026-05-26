from __future__ import annotations

from pathlib import Path
from typing import Any

import pydicom

from config.config import DICOM_ARCHIVE_ENABLED, PERSISTENT_OUTPUT_DIR
from app.infrastructure.dicom_archive import DicomArchiveClient


def _dicom_json_value(item: dict[str, Any], tag: str) -> Any:
    values = item.get(tag, {}).get("Value") or []
    if not values:
        return ""
    value = values[0]
    if isinstance(value, dict):
        return value.get("Alphabetic") or value.get("Ideographic") or value.get("Phonetic") or ""
    return value


def _normalize_archive_study(item: dict[str, Any]) -> dict[str, Any]:
    modalities = item.get("00080061", {}).get("Value") or []
    return {
        "StudyInstanceUID": _dicom_json_value(item, "0020000D"),
        "PatientName": _dicom_json_value(item, "00100010") or "Anonymous",
        "PatientID": _dicom_json_value(item, "00100020"),
        "StudyDate": _dicom_json_value(item, "00080020"),
        "AccessionNumber": _dicom_json_value(item, "00080050"),
        "StudyDescription": _dicom_json_value(item, "00081030"),
        "ModalitiesInStudy": modalities if isinstance(modalities, list) else [modalities],
        "source": "archive",
    }


def _study_from_dataset(ds: pydicom.Dataset) -> dict[str, Any]:
    modality = str(getattr(ds, "Modality", "") or "")
    return {
        "StudyInstanceUID": str(getattr(ds, "StudyInstanceUID", "") or ""),
        "PatientName": str(getattr(ds, "PatientName", "") or "Anonymous"),
        "PatientID": str(getattr(ds, "PatientID", "") or ""),
        "StudyDate": str(getattr(ds, "StudyDate", "") or ""),
        "AccessionNumber": str(getattr(ds, "AccessionNumber", "") or ""),
        "StudyDescription": str(getattr(ds, "StudyDescription", "") or ""),
        "ModalitiesInStudy": [modality] if modality else [],
        "source": "local",
    }


def _matches_filters(
    study: dict[str, Any],
    *,
    patient_id: str | None,
    study_date: str | None,
    modality: str | None,
) -> bool:
    if patient_id and study.get("PatientID") != patient_id:
        return False
    if study_date and study.get("StudyDate") != study_date:
        return False
    if modality and modality not in (study.get("ModalitiesInStudy") or []):
        return False
    return True


async def _list_archive_studies(
    *,
    limit: int,
    offset: int,
    patient_id: str | None,
    study_date: str | None,
    modality: str | None,
) -> list[dict[str, Any]]:
    archive_items = await DicomArchiveClient().search_studies(
        limit=limit,
        offset=offset,
        patient_id=patient_id,
        study_date=study_date,
        modality=modality,
    )
    return [_normalize_archive_study(item) for item in archive_items]


def _list_local_studies(
    *,
    limit: int,
    offset: int,
    patient_id: str | None,
    study_date: str | None,
    modality: str | None,
) -> list[dict[str, Any]]:
    studies_root = Path(PERSISTENT_OUTPUT_DIR) / "studies"
    if not studies_root.exists():
        return []

    studies: dict[str, dict[str, Any]] = {}
    for dicom_path in studies_root.glob("*/*/*.dcm"):
        try:
            ds = pydicom.dcmread(str(dicom_path), stop_before_pixels=True, force=True)
            study = _study_from_dataset(ds)
            study_uid = study.get("StudyInstanceUID")
            if not study_uid or study_uid in studies:
                continue
            if _matches_filters(study, patient_id=patient_id, study_date=study_date, modality=modality):
                studies[study_uid] = study
        except Exception:
            continue

    ordered = sorted(studies.values(), key=lambda item: item.get("StudyDate", ""), reverse=True)
    return ordered[offset : offset + limit]


async def list_studies(
    *,
    limit: int = 100,
    offset: int = 0,
    patient_id: str | None = None,
    study_date: str | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    if DICOM_ARCHIVE_ENABLED:
        try:
            return await _list_archive_studies(
                limit=limit,
                offset=offset,
                patient_id=patient_id,
                study_date=study_date,
                modality=modality,
            )
        except Exception:
            pass

    return _list_local_studies(
        limit=limit,
        offset=offset,
        patient_id=patient_id,
        study_date=study_date,
        modality=modality,
    )
