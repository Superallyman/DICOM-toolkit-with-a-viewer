# app/utilities/anon_utils.py
from __future__ import annotations

from typing import Optional, Dict, Any, Iterable
import pydicom
from pydicom.dataset import FileDataset
from pydicom.datadict import tag_for_keyword
from pydicom.uid import generate_uid

# A pragmatic subset of identifying attributes to clear by default
_DEFAULT_CLEAR: Iterable[str] = (
    "PatientName", "PatientID", "PatientBirthDate", "PatientBirthTime", "PatientSex",
    "OtherPatientIDs", "OtherPatientIDsSequence", "OtherPatientNames",
    "PatientAddress", "EthnicGroup", "PatientComments", "IssuerOfPatientID",
    "ReferringPhysicianName", "PhysiciansOfRecord", "PerformingPhysicianName",
    "OperatorsName", "RequestingPhysician", "InstitutionName", "InstitutionAddress",
    "StudyID", "AccessionNumber",
)

def _delete_keyword(ds: FileDataset, keyword: str) -> None:
    tag = tag_for_keyword(keyword)
    if tag and tag in ds:
        del ds[tag]
    else:
        # best-effort by attribute access (tolerates private mapping sometimes)
        if hasattr(ds, keyword):
            try:
                delattr(ds, keyword)
            except Exception:
                pass

def _replace_keyword(ds: FileDataset, keyword: str, value: Any) -> None:
    try:
        setattr(ds, keyword, value)
    except Exception:
        tag = tag_for_keyword(keyword)
        if tag:
            ds[tag].value = value  # may still fail for VR mismatch; ignore silently

def anonymize_dicom_file(
    in_file: str,
    out_file: str,
    extra_anonymization_rules: Optional[Dict[str, Any]] = None,
    delete_private_tags: bool = True,
) -> None:
    """
    Minimal, safe anonymizer compatible with your endpoint's expectations.
    - Clears common PHI tags
    - Removes private tags (optional)
    - Applies optional rules: {"delete":[...], "replace":{...}, "replace_uids":bool}
    - Leaves Study/Series/SOP UIDs intact by default (to keep your PRE/POST audit comparisons stable)
    """
    ds: FileDataset = pydicom.dcmread(in_file, force=True)

    # 1) remove private tags if requested
    if delete_private_tags:
        ds.remove_private_tags()

    # 2) clear a default set of identifying attributes
    for kw in _DEFAULT_CLEAR:
        _delete_keyword(ds, kw)

    # Mark as de-identified
    _replace_keyword(ds, "PatientIdentityRemoved", "YES")
    _replace_keyword(ds, "DeidentificationMethod", "Basic profile (local)")

    # 3) apply user-provided rules (optional)
    rules = extra_anonymization_rules or {}
    # delete: list of DICOM keywords to drop
    for kw in rules.get("delete", []) or []:
        if isinstance(kw, str):
            _delete_keyword(ds, kw)

    # replace: mapping keyword -> value
    for kw, val in (rules.get("replace") or {}).items():
        if isinstance(kw, str):
            _replace_keyword(ds, kw, val)

    # optionally regenerate UIDs (off by default to preserve your current logic)
    if bool(rules.get("replace_uids")):
        study_uid = str(getattr(ds, "StudyInstanceUID", generate_uid()))
        series_uid = str(getattr(ds, "SeriesInstanceUID", generate_uid()))
        sop_uid = str(getattr(ds, "SOPInstanceUID", generate_uid()))

        ds.StudyInstanceUID = study_uid or generate_uid()
        ds.SeriesInstanceUID = series_uid or generate_uid()
        ds.SOPInstanceUID = sop_uid or generate_uid()

        # keep file meta consistent
        if getattr(ds, "file_meta", None) is not None:
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            if getattr(ds, "SOPClassUID", None):
                ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID

    # 4) write output with a proper meta/preamble
    ds.save_as(out_file, write_like_original=False)
