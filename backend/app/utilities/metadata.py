from datetime import datetime
from pathlib import Path
from typing import Dict, List , Any
import uuid
from pydicom.uid import generate_uid

def populate_required_dicom_tags(headers: dict, filename: str = "") -> dict:
    now = datetime.now()
    return {
        "StudyInstanceUID": headers.get("StudyInstanceUID") or generate_uid(),
        "SeriesInstanceUID": headers.get("SeriesInstanceUID") or generate_uid(),
        "SOPInstanceUID": headers.get("SOPInstanceUID") or generate_uid(),
        "SOPClassUID": headers.get("SOPClassUID", "1.2.840.10008.5.1.4.1.1.7"),
        "InstanceNumber": headers.get("InstanceNumber", "1"),
        "PatientName": headers.get("PatientName", "Anonymous^Patient"),
        "PatientID": headers.get("PatientID", str(uuid.uuid4())[:12]),
        "PatientBirthDate": headers.get("PatientBirthDate", ""),
        "PatientSex": headers.get("PatientSex", ""),
        "PatientAge": headers.get("PatientAge", ""),
        "PatientWeight": headers.get("PatientWeight", ""),
        "PatientAddress": headers.get("PatientAddress", ""),
        "Modality": headers.get("Modality", "OT"),
        "AccessionNumber": headers.get("AccessionNumber", f"ACC{int(now.timestamp())}"),
        "StudyDate": headers.get("StudyDate", now.strftime("%Y%m%d")),
        "StudyTime": headers.get("StudyTime", now.strftime("%H%M%S")),
        "StudyID": headers.get("StudyID", f"SID{now.strftime('%H%M%S')}"),
        "StudyDescription": headers.get("StudyDescription", "Imported Study"),
        "SeriesDate": headers.get("SeriesDate", now.strftime("%Y%m%d")),
        "SeriesTime": headers.get("SeriesTime", now.strftime("%H%M%S")),
        "SeriesDescription": headers.get("SeriesDescription", "Converted Series"),
    }

REQUIRED_TAGS = ["PatientName", "PatientID", "StudyDate", "Modality", "StudyDescription", "AccessionNumber"]

def validate_metadata(headers: Dict) -> List[str]:
    return [tag for tag in REQUIRED_TAGS if tag not in headers or not headers[tag]]

def extract_metadata_from_filename(filename: str) -> Dict[str, str]:
    name = Path(filename).stem
    parts = name.split("_")
    if len(parts) >= 5:
        return {
            "PatientName": parts[0],
            "PatientID": parts[1],
            "StudyDate": parts[2],
            "Modality": parts[3],
            "StudyDescription": parts[4],
            "AccessionNumber": "AUTO123",
        }
    return {}




# --- Minimal, safe extractor for a pydicom Dataset ---------------------------
def _str(v: Any) -> str:
    try:
        return "" if v is None else str(v)
    except Exception:
        return ""

def get_dicom_metadata(ds) -> Dict[str, str]:
    """
    Return a compact dict of commonly used DICOM header fields from a pydicom Dataset.
    Safe to call even if some attributes are missing.
    """
    wanted = [
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "SOPInstanceUID",
        # (optionally include a few free-text fields useful for audit)
        "StudyDescription",
        "SeriesDescription",
        "ProtocolName",
        "AdditionalPatientHistory",
        "PatientComments",
        "RequestedProcedureDescription",
        "ScheduledProcedureStepDescription",
        "PatientID",
        "PatientName",
    ]
    out: Dict[str, str] = {}
    for name in wanted:
        out[name] = _str(getattr(ds, name, ""))
    return out

# Provide an alias some codebases use
def build_metadata(ds) -> Dict[str, str]:
    return get_dicom_metadata(ds)

# --- Compatibility shim for modules that import `extract_metadata` -----------
def extract_metadata(ds) -> Dict[str, str]:
    """
    Return a compact dict of DICOM metadata used by endpoints.
    This wrapper keeps backward compatibility with modules that import
    `extract_metadata` directly.
    """
    return get_dicom_metadata(ds)


# --- Compatibility shim for modules that import `extract_metadata` ---
# If your file already has a function like `get_dicom_metadata` or `build_metadata`,
# just forward to it here.

def extract_metadata(ds):
    """
    Return a compact dict of DICOM metadata used by endpoints.
    This wrapper keeps backward compatibility with modules that import
    `extract_metadata` directly.
    """
    try:
        # If you already have one of these, forward to it.
        return get_dicom_metadata(ds)           # <-- if this exists in your file
    except NameError:
        pass

    try:
        return build_metadata(ds)               # <-- or this, if you use another name
    except NameError:
        pass

    # Minimal fallback so the API can still run even if above helpers are absent.
    def _s(x): 
        try: 
            return str(x)
        except Exception:
            return ""

    return {
        "StudyInstanceUID": _s(getattr(ds, "StudyInstanceUID", "")),
        "SeriesInstanceUID": _s(getattr(ds, "SeriesInstanceUID", "")),
        "SOPInstanceUID": _s(getattr(ds, "SOPInstanceUID", "")),
    }


