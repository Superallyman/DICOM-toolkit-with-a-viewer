# app/dicomweb_routes.py
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pathlib import Path
import os
import pydicom
from PIL import Image
from io import BytesIO
from pydicom.datadict import keyword_for_tag

from config.config import PERSISTENT_OUTPUT_DIR
from app.utilities.utilities import hash_uid  # resolve_uid_hash not needed here

router = APIRouter(prefix="/dicomweb", tags=["DICOMWeb"])

STUDIES_DIR = os.path.join(PERSISTENT_OUTPUT_DIR, "studies")
PLACEHOLDER_PATH = Path("app/static/missing_thumbnail.jpg")

# ---------------- helpers ----------------

def _dicom_dataset_to_json(ds):
    elements = []
    for elem in ds:
        try:
            if elem.tag.is_private or elem.keyword == "PixelData":
                continue
            if elem.VR == "OB":
                val = elem.value
                if isinstance(val, (bytes, bytearray)) and len(val) > 1024:
                    continue

            value = elem.value
            if isinstance(value, bytes):
                value = value.decode(errors="ignore")
            elif isinstance(value, (list, tuple)):
                value = [str(v) for v in value]
            else:
                value = [str(value)]

            name = keyword_for_tag(elem.tag)
            item = {"vr": elem.VR, "Value": value}
            if name:
                item["Name"] = name
            elements.append(item)
        except Exception:
            continue
    return elements

def _study_dir(study_uid: str) -> Path:
    return Path(STUDIES_DIR) / hash_uid(study_uid)

def _series_dir(study_uid: str, series_uid: str) -> Path:
    return _study_dir(study_uid) / hash_uid(series_uid)

def _instance_path(study_uid: str, series_uid: str, sop_uid: str) -> Path:
    return _series_dir(study_uid, series_uid) / f"{hash_uid(sop_uid)}.dcm"

def _thumb_paths(study_uid: str, series_uid: str, sop_uid: str):
    base = _series_dir(study_uid, series_uid) / f"{hash_uid(sop_uid)}"
    return base.with_suffix(".jpg"), base.with_suffix(".png")

def _gen_thumbnail_simple(ds, out_path: Path, size=(128, 128)):
    arr = ds.pixel_array
    import numpy as np
    arr = np.asarray(arr)
    if arr.size:
        arr = arr.astype("float32")
        rng = float(arr.max() - arr.min())
        if rng > 0:
            arr = (arr - arr.min()) * (255.0 / rng)
    arr = arr.clip(0, 255).astype("uint8")
    from PIL import Image as PILImage
    img = PILImage.fromarray(arr if arr.ndim == 2 else arr[..., :3])
    img.thumbnail(size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG")

def _v(v):
    return [v] if v not in (None, "") else []

def _study_item(ds):
    return {
        "0020000D": {"vr": "UI", "Value": _v(getattr(ds, "StudyInstanceUID", ""))},
        "00080020": {"vr": "DA", "Value": _v(getattr(ds, "StudyDate", ""))},
        "00081030": {"vr": "LO", "Value": _v(getattr(ds, "StudyDescription", ""))},
        "00080061": {"vr": "CS", "Value": _v(getattr(ds, "Modality", ""))},
        "00100010": {"vr": "PN", "Value": _v(str(getattr(ds, "PatientName", "")))},
        "00100020": {"vr": "LO", "Value": _v(getattr(ds, "PatientID", ""))},
        "00080050": {"vr": "SH", "Value": _v(getattr(ds, "AccessionNumber", ""))},
    }

def _series_item(ds):
    return {
        "0020000D": {"vr": "UI", "Value": _v(getattr(ds, "StudyInstanceUID", ""))},
        "0020000E": {"vr": "UI", "Value": _v(getattr(ds, "SeriesInstanceUID", ""))},
        "00080060": {"vr": "CS", "Value": _v(getattr(ds, "Modality", ""))},
        "0008103E": {"vr": "LO", "Value": _v(getattr(ds, "SeriesDescription", ""))},
        "00200011": {"vr": "IS", "Value": _v(getattr(ds, "SeriesNumber", ""))},
    }

def _instance_item(ds):
    return {
        "0020000D": {"vr": "UI", "Value": _v(getattr(ds, "StudyInstanceUID", ""))},
        "0020000E": {"vr": "UI", "Value": _v(getattr(ds, "SeriesInstanceUID", ""))},
        "00080018": {"vr": "UI", "Value": _v(getattr(ds, "SOPInstanceUID", ""))},
        "00080016": {"vr": "UI", "Value": _v(getattr(ds, "SOPClassUID", ""))},
        "00200013": {"vr": "IS", "Value": _v(getattr(ds, "InstanceNumber", ""))},
    }

def _safe_dcmread(path: Path, *, stop_before_pixels=True):
    try:
        return pydicom.dcmread(str(path), force=True, stop_before_pixels=stop_before_pixels)
    except Exception:
        return None

# ---------------- QIDO: studies ----------------

@router.get("/studies")
def list_studies(
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    PatientID: str | None = Query(None),
    StudyDate: str | None = Query(None),
    Modality: str | None = Query(None),
):
    studies_path = Path(STUDIES_DIR)
    if not studies_path.exists():
        raise HTTPException(status_code=404, detail="Studies directory not found")

    results = []
    for study_hash in os.listdir(studies_path):
        study_dir = studies_path / study_hash
        if not study_dir.is_dir():
            continue
        found = False
        for series_hash in os.listdir(study_dir):
            series_dir = study_dir / series_hash
            if not series_dir.is_dir():
                continue
            for sop_file in series_dir.glob("*.dcm"):
                ds = _safe_dcmread(sop_file)
                if ds is None:
                    continue
                item = _study_item(ds)

                pid = (item.get("00100020", {}).get("Value") or [None])[0]
                sdate = (item.get("00080020", {}).get("Value") or [None])[0]
                mod = (item.get("00080061", {}).get("Value") or [None])[0]

                if PatientID and pid != PatientID:
                    continue
                if StudyDate and sdate != StudyDate:
                    continue
                if Modality and mod != Modality:
                    continue

                results.append(item)
                found = True
                break
            if found:
                break

    return JSONResponse(content=results[offset: offset + limit], media_type="application/dicom+json")

# ---------------- QIDO: series ----------------

@router.get("/studies/{study_uid}/series")
def get_series(
    study_uid: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    Modality: str | None = Query(None),
):
    study_dir = _study_dir(study_uid)
    if not study_dir.exists():
        raise HTTPException(status_code=404, detail="Study not found")

    results = []
    for series_hash in os.listdir(study_dir):
        series_dir = study_dir / series_hash
        if not series_dir.is_dir():
            continue
        for sop_file in series_dir.glob("*.dcm"):
            ds = _safe_dcmread(sop_file)
            if ds is None:
                continue
            item = _series_item(ds)
            mod = (item.get("00080060", {}).get("Value") or [None])[0]
            if Modality and mod != Modality:
                continue
            results.append(item)
            break

    return JSONResponse(content=results[offset: offset + limit], media_type="application/dicom+json")

# ---------------- QIDO: instances ----------------

@router.get("/studies/{study_uid}/series/{series_uid}/instances")
def get_instances(
    study_uid: str,
    series_uid: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
):
    series_dir = _series_dir(study_uid, series_uid)
    if not series_dir.exists():
        raise HTTPException(status_code=404, detail="Series not found")

    results = []
    for sop_file in series_dir.glob("*.dcm"):
        ds = _safe_dcmread(sop_file)
        if ds is None:
            continue
        results.append(_instance_item(ds))

    return JSONResponse(content=results[offset: offset + limit], media_type="application/dicom+json")

# ---------------- WADO: instance metadata ----------------

@router.get("/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}/metadata")
def get_instance_metadata(study_uid: str, series_uid: str, sop_uid: str, request: Request):
    dcm_path = _instance_path(study_uid, series_uid, sop_uid)
    if not dcm_path.exists():
        raise HTTPException(status_code=404, detail="DICOM file not found")

    ds = _safe_dcmread(dcm_path)
    if ds is None:
        raise HTTPException(status_code=422, detail="Unreadable DICOM instance")
    return JSONResponse(content=[_instance_item(ds)], media_type="application/dicom+json")

# ---------------- WADO: full instance ----------------

@router.get("/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}")
def get_instance(study_uid: str, series_uid: str, sop_uid: str):
    dcm_path = _instance_path(study_uid, series_uid, sop_uid)
    if not dcm_path.exists():
        raise HTTPException(status_code=404, detail="DICOM file not found")
    return FileResponse(path=str(dcm_path), media_type="application/dicom", filename=f"{sop_uid}.dcm")

# ---------------- Thumbnails ----------------

@router.get("/thumbnails/{study_uid}/{series_uid}/{sop_uid}")
def get_thumbnail(study_uid: str, series_uid: str, sop_uid: str, request: Request, size: int | None = Query(None, gt=0, le=1024)):
    jpg_path, png_path = _thumb_paths(study_uid, series_uid, sop_uid)
    dcm_path = _instance_path(study_uid, series_uid, sop_uid)

    accept = (request.headers.get("accept") or "*/*").lower()
    headers = {"Content-Disposition": "inline"}

    def serve_image(img_path: Path, mime_type: str):
        if size is None:
            return FileResponse(path=str(img_path), media_type=mime_type, headers=headers)
        try:
            with Image.open(img_path) as img:
                img.thumbnail((size, size))
                buffer = BytesIO()
                fmt = "JPEG" if mime_type == "image/jpeg" else "PNG"
                img.save(buffer, format=fmt)
                buffer.seek(0)
                return StreamingResponse(buffer, media_type=mime_type, headers=headers)
        except Exception:
            raise HTTPException(status_code=500, detail="Thumbnail load failed")

    if not jpg_path.exists() and not png_path.exists() and dcm_path.exists():
        ds = _safe_dcmread(dcm_path, stop_before_pixels=False)
        if ds is not None:
            try:
                _gen_thumbnail_simple(ds, jpg_path)
            except Exception:
                pass

    if "image/png" in accept and png_path.exists():
        return serve_image(png_path, "image/png")
    if ("image/jpeg" in accept or "*/*" in accept) and jpg_path.exists():
        return serve_image(jpg_path, "image/jpeg")

    if jpg_path.exists():
        return serve_image(jpg_path, "image/jpeg")
    if png_path.exists():
        return serve_image(png_path, "image/png")
    if PLACEHOLDER_PATH.exists():
        return FileResponse(path=str(PLACEHOLDER_PATH), media_type="image/jpeg", headers=headers)

    raise HTTPException(status_code=404, detail="Thumbnail not found")

# ---------------- OHIF-friendly metadata (single definitions) ----------------

@router.get("/studies/{study_uid}/series/{series_uid}/metadata")
def get_series_metadata(study_uid: str, series_uid: str):
    series_dir = _series_dir(study_uid, series_uid)
    if not series_dir.exists():
        raise HTTPException(status_code=404, detail="Series not found")

    items = []
    for sop_path in series_dir.glob("*.dcm"):
        ds = _safe_dcmread(sop_path)
        if ds is None:
            continue
        items.append(_instance_item(ds))
    return JSONResponse(content=items, media_type="application/dicom+json")

@router.get("/studies/{study_uid}/metadata")
def get_study_metadata(study_uid: str):
    study_dir = _study_dir(study_uid)
    if not study_dir.exists():
        raise HTTPException(status_code=404, detail="Study not found")

    items = []
    for series_hash in os.listdir(study_dir):
        series_dir = study_dir / series_hash
        if not series_dir.is_dir():
            continue
        for sop_path in series_dir.glob("*.dcm"):
            ds = _safe_dcmread(sop_path)
            if ds is None:
                continue
            items.append(_instance_item(ds))
    return JSONResponse(content=items, media_type="application/dicom+json")

@router.get("/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}/frames/{frame_number}")
def get_instance_frame(study_uid: str, series_uid: str, sop_uid: str, frame_number: int):
    dcm_path = _instance_path(study_uid, series_uid, sop_uid)
    if not dcm_path.exists():
        raise HTTPException(status_code=404, detail="DICOM file not found")

    ds = _safe_dcmread(dcm_path, stop_before_pixels=False)
    if ds is None:
        raise HTTPException(status_code=422, detail="Unreadable DICOM instance")

    arr = ds.pixel_array
    import numpy as np
    arr = np.asarray(arr)

    if arr.ndim == 3 and getattr(ds, "NumberOfFrames", 1) > 1:
        idx = max(0, min(frame_number - 1, arr.shape[0] - 1))
        frame = arr[idx]
    else:
        frame = arr

    frame = frame.astype("float32")
    rng = float(frame.max() - frame.min()) if frame.size else 0.0
    if rng > 0:
        frame = (frame - frame.min()) * (255.0 / rng)
    frame = frame.clip(0, 255).astype("uint8")

    img = Image.fromarray(frame if frame.ndim == 2 else frame[..., :3])
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")
