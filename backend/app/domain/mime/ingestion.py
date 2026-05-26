# app/domain/mime/ingestion.py
from __future__ import annotations

# --- stdlib ---
import io
import os
import re
import inspect
from datetime import datetime
from email import message_from_bytes
from email.message import Message
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --- third-party ---
from fastapi import HTTPException, Request, UploadFile
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

import pydicom
from pydicom.uid import (
    generate_uid,
    SecondaryCaptureImageStorage,
    ExplicitVRLittleEndian,
)
from pydicom.dataset import Dataset, FileDataset

# Optional deps for image decoding → uncompressed Secondary Capture DICOM
try:
    from PIL import Image
    import numpy as np

    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False

# --- app imports (absolute, stable for VS Code/Pylance & runtime) ---
from app.db.models import ConversionLog
from app.utilities.metadata import extract_metadata
from app.utilities.utilities import ensure_directory_exists, copy_dicom_to_ohif
from app.utilities.thumbnail_dao import generate_thumbnail
from app.utilities.logging_utils import save_dicom_metadata, log_conversion
from app.utilities.endpoint_helpers import log_dicom_metadata
from app.utilities.url_helpers import public_api_v1_base_url, public_ohif_base_url
from app.infrastructure.dicom_archive import store_dicom_file_best_effort

# --- paths/config (use config if present; fall back to sensible defaults) ---
try:
    from config.config import PERSISTENT_OUTPUT_DIR, OHIF_VIEWER_DIR

    persistent_output_base = Path(PERSISTENT_OUTPUT_DIR)
    ohif_viewer_path = Path(OHIF_VIEWER_DIR)
except Exception:
    PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app")).resolve()
    persistent_output_base = PROJECT_ROOT / "persistent_output"
    ohif_viewer_path = PROJECT_ROOT / "ohif"

# ---------- helpers ----------


async def _publish_dicom_for_viewing(dicom_path: str) -> None:
    """Publish to the local study cache and the configured DICOM archive."""
    try:
        copy_dicom_to_ohif(dicom_path, str(ohif_viewer_path))
    except Exception as e:
        logger.warning(f"[OHIF] copy failed (ignored): {e}")

    await store_dicom_file_best_effort(dicom_path)


def _is_dicom_bytes(b: bytes) -> bool:
    """
    Conservative DICOM sniff:
      - True if Part-10 preamble present ("DICM" at offset 128)
      - Else try a normal read (no force). If that fails, try force=True
        but only accept if core DICOM identity tags exist.
    """
    if len(b) >= 132 and b[128:132] == b"DICM":
        return True

    bio = io.BytesIO(b)

    # Try a normal, non-forced read first
    try:
        _ = pydicom.dcmread(bio, force=False, stop_before_pixels=True)
        return True
    except Exception:
        pass

    # Fall back to a forced read, but require core identity tags
    try:
        bio.seek(0)
        ds = pydicom.dcmread(bio, force=True, stop_before_pixels=True)
        has_file_meta = getattr(ds, "file_meta", None) is not None and (
            getattr(ds.file_meta, "MediaStorageSOPClassUID", None) is not None
        )
        has_ids = hasattr(ds, "SOPClassUID") or hasattr(ds, "StudyInstanceUID")
        return bool(has_file_meta or has_ids)
    except Exception:
        return False


def _looks_like_imaging(ds: "pydicom.dataset.FileDataset") -> bool:
    """
    True if dataset is likely an imaging object.
    We treat anything with PixelData as imaging.
    Otherwise, accept common Image Storage SOP Class UID family.
    """
    if hasattr(ds, "PixelData") or hasattr(ds, "FloatPixelData") or hasattr(ds, "DoubleFloatPixelData"):
        return True
    sop = str(getattr(ds, "SOPClassUID", "") or "")
    # All image storage classes are under 1.2.840.10008.5.1.4.1.1.*
    return sop.startswith("1.2.840.10008.5.1.4.1.1.")



def _extract_candidate_parts(msg: Message) -> List[Tuple[str, bytes]]:
    """
    Use the stdlib email parser first. Be slightly more permissive in detecting DICOM.
    """
    out: List[Tuple[str, bytes]] = []
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True) or b""
        if _is_dicom_bytes(payload):
            out.append((msg.get_filename() or "payload.dcm", payload))
        return out

    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        payload = part.get_payload(decode=True) or b""
        filename = (part.get_filename("") or "").lower()

        looks_like_dicom = (
            "application/dicom" in ctype
            or "dicom" in ctype
            or filename.endswith(".dcm")
            or _is_dicom_bytes(payload)
        )
        if looks_like_dicom and payload:
            out.append((part.get_filename() or "attachment.dcm", payload))
    return out


def _parse_boundary_only_mime(raw: bytes) -> list[tuple[str, bytes, str]]:
    """
    Fallback parser for ad-hoc boundary-only MIME blobs (no top-level headers).
    Returns list of (filename, payload_bytes, content_type).
    """
    text = raw.decode("latin-1", errors="ignore")

    # The first non-empty line should be the opening boundary line: e.g. "--BOUNDARY_abc"
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first_line.startswith("--"):
        return []

    boundary = first_line[2:].strip()  # remove leading "--"
    # Match delimiter lines exactly (opening or closing)
    delim_re = re.compile(rf"(?m)^\s*--{re.escape(boundary)}(--)?\s*$")
    matches = list(delim_re.finditer(text))
    if not matches:
        return []

    parts: list[tuple[str, bytes, str]] = []
    for i in range(len(matches) - 1):
        _, end_prev = matches[i].span()
        start_next, _ = matches[i + 1].span()
        is_close_prev = matches[i].group(1) is not None
        is_close_next = matches[i + 1].group(1) is not None

        if is_close_prev:
            break

        segment = text[end_prev:start_next].lstrip("\r\n")
        split = re.split(r"\r?\n\r?\n", segment, maxsplit=1)
        if len(split) != 2:
            continue
        headers_str, body_str = split

        headers: dict[str, str] = {}
        for line in headers_str.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        ctype = headers.get("content-type", "").lower()
        cte = headers.get("content-transfer-encoding", "").lower()
        disp = headers.get("content-disposition", "")

        # Filename from Content-Disposition if present
        name = None
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\r\n]+)"?', disp, flags=re.I)
        if m:
            name = m.group(1)

        if not name:
            ext = ""
            if "image/jpeg" in ctype or "image/jpg" in ctype:
                ext = ".jpg"
            elif "image/jls" in ctype or "jpeg-ls" in ctype:
                ext = ".jls"
            elif "application/dicom" in ctype:
                ext = ".dcm"
            name = f"part_{len(parts)}{ext}"

        # Decode body by CTE
        if cte == "base64":
            import base64
            body_bytes = base64.b64decode(re.sub(r"\s+", "", body_str))
        elif cte in ("quoted-printable", "qp"):
            import quopri
            body_bytes = quopri.decodestring(body_str)
        else:
            body_bytes = body_str.encode("latin-1", errors="ignore")

        parts.append((name, body_bytes, ctype))
        if is_close_next:
            break

    return parts



def _persist_dicom_bytes(b: bytes, base_out: Path) -> Tuple[str, str, str, str]:
    """
    Save DICOM bytes; return (path, StudyUID, SeriesUID, SOPUID).
    Supports raw datasets that lack Part-10 file meta by synthesizing it so we can write a valid file.
    """
    ds = pydicom.dcmread(io.BytesIO(b), force=True)

    # Ensure core UIDs
    study_uid = getattr(ds, "StudyInstanceUID", None) or generate_uid()
    series_uid = getattr(ds, "SeriesInstanceUID", None) or generate_uid()
    sop_uid = getattr(ds, "SOPInstanceUID", None) or generate_uid()
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid

    # Ensure File Meta (Part-10 header) exists
    from pydicom.dataset import Dataset as PydicomDataset

    need_meta = (
        not hasattr(ds, "file_meta")
        or ds.file_meta is None
        or not getattr(ds.file_meta, "MediaStorageSOPClassUID", None)
        or not getattr(ds.file_meta, "MediaStorageSOPInstanceUID", None)
        or not getattr(ds.file_meta, "TransferSyntaxUID", None)
    )

    if need_meta:
        file_meta = PydicomDataset()
        sop_class = getattr(ds, "SOPClassUID", None) or SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPClassUID = sop_class
        file_meta.MediaStorageSOPInstanceUID = sop_uid
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = file_meta
        ds.is_little_endian = True
        ds.is_implicit_VR = False

    # Persist
    study_dir = base_out / study_uid / series_uid
    ensure_directory_exists(str(study_dir))
    out_path = study_dir / f"{sop_uid}.dcm"
    ds.save_as(str(out_path), write_like_original=False)

    return str(out_path), study_uid, series_uid, sop_uid


def _wrap_image_as_sc_dicom(
    image_bytes: bytes,
    base_out: Path,
    study_uid: str | None = None,
    series_uid: str | None = None,
) -> Tuple[str, str, str, str]:
    """
    Convert a non-DICOM image to an uncompressed Secondary Capture DICOM.
    Returns (path, StudyUID, SeriesUID, SOPUID).
    """
    import numpy as np

    # Decode → ndarray
    arr = _decode_image_bytes(image_bytes)

    # Shape / channels
    if arr.ndim == 2:
        samples_per_pixel = 1
    elif arr.ndim == 3:
        if arr.shape[2] > 3:
            arr = arr[:, :, :3]
        samples_per_pixel = arr.shape[2]
    else:
        raise RuntimeError(f"Unsupported decoded image shape: {arr.shape}")

    # Bit depth → PixelRepresentation/Allocated/Stored/HighBit
    if arr.dtype == np.uint8:
        bits_allocated = bits_stored = 8
        high_bit = 7
        pixel_repr = 0
    elif arr.dtype == np.uint16:
        bits_allocated = bits_stored = 16
        high_bit = 15
        pixel_repr = 0
    else:
        if getattr(arr, "max", lambda: 0)() > 255:
            arr = arr.astype(np.uint16, copy=False)
            bits_allocated = bits_stored = 16
            high_bit = 15
        else:
            arr = arr.astype(np.uint8, copy=False)
            bits_allocated = bits_stored = 8
            high_bit = 7
        pixel_repr = 0

    rows, cols = int(arr.shape[0]), int(arr.shape[1])
    photometric = "MONOCHROME2" if samples_per_pixel == 1 else "RGB"

    # For nicer initial display, compute extrema now (used below)
    try:
        smallest = int(arr.min())
        largest  = int(arr.max())
    except Exception:
        smallest = 0
        largest  = (1 << bits_stored) - 1

    now = datetime.now()
    study_uid  = study_uid  or generate_uid()
    series_uid = series_uid or generate_uid()
    sop_uid    = generate_uid()

    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID    = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID          = ExplicitVRLittleEndian

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.SOPClassUID        = SecondaryCaptureImageStorage
    ds.SOPInstanceUID     = sop_uid
    ds.Modality           = "OT"
    ds.StudyInstanceUID   = study_uid
    ds.SeriesInstanceUID  = series_uid
    ds.PatientName        = "Unknown"
    ds.PatientID          = "Unknown"
    ds.StudyDate          = now.strftime("%Y%m%d")
    ds.StudyTime          = now.strftime("%H%M%S")
    ds.SeriesNumber       = 1
    ds.InstanceNumber     = 1
    ds.BurnedInAnnotation = "NO"
    ds.LossyImageCompression = "00"

    # Image Pixel Module
    ds.SamplesPerPixel            = samples_per_pixel
    ds.PhotometricInterpretation  = photometric
    ds.Rows                       = rows
    ds.Columns                    = cols
    ds.BitsAllocated              = bits_allocated
    ds.BitsStored                 = bits_stored
    ds.HighBit                    = high_bit
    ds.PixelRepresentation        = pixel_repr

    # Viewer-friendly VOI (grayscale only)
    if samples_per_pixel == 1:
        try:
            import numpy as _np
            lo = int(_np.percentile(arr, 1))
            hi = int(_np.percentile(arr, 99))
            if hi <= lo:
                lo, hi = smallest, largest
        except Exception:
            lo, hi = smallest, largest
        ww = max(1, hi - lo)
        wc = lo + ww // 2
        ds.WindowCenter = float(wc)
        ds.WindowWidth  = float(ww)
        ds.SmallestImagePixelValue = smallest
        ds.LargestImagePixelValue  = largest

    # PixelData
    if samples_per_pixel == 1:
        ds.PixelData = arr.tobytes(order="C")
    else:
        arr = arr[:, :, :3].copy(order="C")
        ds.PixelData = arr.tobytes(order="C")
        ds.PlanarConfiguration = 0  # RGBRGB…

    # Save
    study_dir = base_out / study_uid / series_uid
    ensure_directory_exists(str(study_dir))
    out_path = study_dir / f"{sop_uid}.dcm"
    ds.is_little_endian = True
    ds.is_implicit_VR   = False
    ds.save_as(str(out_path), write_like_original=False)
    return str(out_path), study_uid, series_uid, sop_uid





def build_ohif_url(request: Request, study_uid: str, series_uid: str | None = None, sop_uid: str | None = None) -> str:
    base = public_ohif_base_url(request)
    # Primary (query-param) style
    q = f"StudyInstanceUIDs={study_uid}"
    if series_uid:
        q += f"&SeriesInstanceUID={series_uid}"
    if sop_uid:
        q += f"&SOPInstanceUID={sop_uid}"
    return f"{base}/viewer?{q}"


async def _download_url_for_output(request: Request, session: AsyncSession, output_file: str | Path) -> str:
    output_path = str(output_file)
    try:
        result = await session.execute(
            select(ConversionLog)
            .where(ConversionLog.output_file == output_path)
            .order_by(ConversionLog.timestamp.desc())
            .limit(1)
        )
        conversion = result.scalar_one_or_none()
        if conversion is not None:
            return f"{public_api_v1_base_url(request)}/files/{conversion.id}/download"
    except Exception as exc:
        logger.warning(f"[DOWNLOAD] conversion-id lookup failed: {exc}")

    return f"{public_api_v1_base_url(request)}/files/download?file_path={output_path}"



async def _log_dicom_metadata_compat(
    ds,
    session=None,
    study_uid: str | None = None,
    series_uid: str | None = None,
    sop_uid: str | None = None,
    phase: str = "pre",
):
    """
    Prefer the current signature:
      log_dicom_metadata(session, *, study_uid, series_uid=None, sop_uid=None, ds, phase='post')
    Fallback (compatibility builds):
      log_dicom_metadata(ds)
    """
    # Try the modern keyword-only signature
    try:
        maybe = log_dicom_metadata(
            session,
            study_uid=study_uid or "",
            series_uid=series_uid or "",
            sop_uid=sop_uid or "",
            ds=ds,
            phase=phase,
        )
        if inspect.isawaitable(maybe):
            await maybe
        return
    except TypeError:
        # Fallback to the single-argument compatibility form.
        try:
            maybe = log_dicom_metadata(ds)  # type: ignore[arg-type]
            if inspect.isawaitable(maybe):
                await maybe
        except Exception as e:
            logger.warning(f"[LOG] dicom_metadata compatibility call failed: {e}")
    except Exception as e:
        logger.warning(f"[LOG] dicom_metadata (keyword) failed: {e}")


def _decode_image_bytes(image_bytes: bytes):
    """
    Return a NumPy array from raw image bytes.

    Order:
      1) Pillow (if available; JPEG-LS only with pillow-jpls)
      2) imagecodecs.*jpegls* decoders (multiple names across versions)
      3) imagecodecs.imread (generic convenience reader)
      4) glymur (JPEG 2000)

    Returns np.ndarray (H,W) or (H,W,C), dtype uint8/uint16.
    """
    # 1) Pillow
    try:
        if _PIL_OK:
            from PIL import Image as _Image
            import numpy as _np
            with _Image.open(io.BytesIO(image_bytes)) as im:
                if im.mode in ("I;16", "I;16B", "I;16L"):
                    arr = _np.array(im, dtype=_np.uint16)
                else:
                    if im.mode not in ("L", "RGB"):
                        im = im.convert("RGB")
                    arr = _np.array(im)
            logger.info("[DECODE] Pillow succeeded")
            return arr
    except Exception as e:
        logger.debug(f"[DECODE] Pillow failed: {e!r}")

    # 2) imagecodecs – JPEG-LS functions vary by build
    try:
        import imagecodecs as _ic
        import numpy as _np

        last_err = None
        for fn_name in ("jpeg_ls_decode", "jpegls_decode", "jpegls_decode"):
            try:
                fn = getattr(_ic, fn_name, None)
                if fn is None:
                    continue
                arr = fn(image_bytes)
                if arr.dtype not in (_np.uint8, _np.uint16):
                    arr = arr.astype(_np.uint16 if getattr(arr, "max", lambda: 0)() > 255 else _np.uint8, copy=False)
                logger.info(f"[DECODE] imagecodecs.{fn_name} succeeded")
                return arr
            except Exception as e:
                last_err = e
                logger.debug(f"[DECODE] imagecodecs.{fn_name} failed: {e!r}")

        # 2b) Generic reader
        try:
            arr = _ic.imread(image_bytes)
            if arr.dtype not in (_np.uint8, _np.uint16):
                arr = arr.astype(_np.uint16 if getattr(arr, "max", lambda: 0)() > 255 else _np.uint8, copy=False)
            logger.info("[DECODE] imagecodecs.imread succeeded")
            return arr
        except Exception as e:
            logger.debug(f"[DECODE] imagecodecs.imread failed: {e!r}")
            if last_err:
                logger.debug(f"[DECODE] Last JLS error: {last_err!r}")
    except Exception as e:
        logger.debug(f"[DECODE] imagecodecs import/dispatch failed: {e!r}")

    # 3) glymur (JPEG2000)
    try:
        import glymur  # type: ignore
        import numpy as _np
        jp2 = glymur.Jp2k(io.BytesIO(image_bytes))
        arr = _np.asarray(jp2[:])
        if arr.dtype not in (_np.uint8, _np.uint16):
            arr = arr.astype(_np.uint16 if getattr(arr, "max", lambda: 0)() > 255 else _np.uint8, copy=False)
        if arr.ndim == 3 and arr.shape[2] == 1:
            arr = arr[:, :, 0]
        logger.info("[DECODE] glymur succeeded")
        return arr
    except Exception as e:
        logger.debug(f"[DECODE] glymur failed: {e!r}")

    # Diagnostics + raise
    try:
        import binascii
        sig_hex = binascii.hexlify(image_bytes[:8]).decode("ascii")
    except Exception:
        sig_hex = str(image_bytes[:8])
    logger.warning(f"[DECODE] No decoder succeeded. First 8 bytes: 0x{sig_hex}")
    raise RuntimeError(
        "No decoder available for this image format. "
        "Tried: Pillow, imagecodecs (jpeg_ls/jpegls + imread), glymur."
    )



def _wrap_image_as_sc_dicom(
    image_bytes: bytes,
    base_out: Path,
    study_uid: str | None = None,
    series_uid: str | None = None,
) -> Tuple[str, str, str, str]:
    """
    Convert a non-DICOM image to an uncompressed Secondary Capture DICOM.
    Returns (path, StudyUID, SeriesUID, SOPUID).
    """
    import numpy as np

    # Decode → ndarray
    arr = _decode_image_bytes(image_bytes)

    # Shape / channels
    if arr.ndim == 2:
        samples_per_pixel = 1
    elif arr.ndim == 3:
        if arr.shape[2] > 3:
            arr = arr[:, :, :3]
        samples_per_pixel = arr.shape[2]
    else:
        raise RuntimeError(f"Unsupported decoded image shape: {arr.shape}")

    # Bit depth → PixelRepresentation/Allocated/Stored/HighBit
    if arr.dtype == np.uint8:
        bits_allocated = bits_stored = 8
        high_bit = 7
        pixel_repr = 0
    elif arr.dtype == np.uint16:
        bits_allocated = bits_stored = 16
        high_bit = 15
        pixel_repr = 0
    else:
        if getattr(arr, "max", lambda: 0)() > 255:
            arr = arr.astype(np.uint16, copy=False)
            bits_allocated = bits_stored = 16
            high_bit = 15
        else:
            arr = arr.astype(np.uint8, copy=False)
            bits_allocated = bits_stored = 8
            high_bit = 7
        pixel_repr = 0

    rows, cols = int(arr.shape[0]), int(arr.shape[1])
    photometric = "MONOCHROME2" if samples_per_pixel == 1 else "RGB"

    # For nicer initial display, compute extrema now (used below)
    try:
        smallest = int(arr.min())
        largest  = int(arr.max())
    except Exception:
        smallest = 0
        largest  = (1 << bits_stored) - 1

    now = datetime.now()
    study_uid  = study_uid  or generate_uid()
    series_uid = series_uid or generate_uid()
    sop_uid    = generate_uid()

    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID    = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID          = ExplicitVRLittleEndian

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.SOPClassUID        = SecondaryCaptureImageStorage
    ds.SOPInstanceUID     = sop_uid
    ds.Modality           = "OT"
    ds.StudyInstanceUID   = study_uid
    ds.SeriesInstanceUID  = series_uid
    ds.PatientName        = "Unknown"
    ds.PatientID          = "Unknown"
    ds.StudyDate          = now.strftime("%Y%m%d")
    ds.StudyTime          = now.strftime("%H%M%S")
    ds.SeriesNumber       = 1
    ds.InstanceNumber     = 1
    ds.BurnedInAnnotation = "NO"
    ds.LossyImageCompression = "00"

    # Image Pixel Module
    ds.SamplesPerPixel            = samples_per_pixel
    ds.PhotometricInterpretation  = photometric
    ds.Rows                       = rows
    ds.Columns                    = cols
    ds.BitsAllocated              = bits_allocated
    ds.BitsStored                 = bits_stored
    ds.HighBit                    = high_bit
    ds.PixelRepresentation        = pixel_repr

    # Viewer-friendly VOI (grayscale only)
    if samples_per_pixel == 1:
        try:
            import numpy as _np
            lo = int(_np.percentile(arr, 1))
            hi = int(_np.percentile(arr, 99))
            if hi <= lo:
                lo, hi = smallest, largest
        except Exception:
            lo, hi = smallest, largest
        ww = max(1, hi - lo)
        wc = lo + ww // 2
        ds.WindowCenter = float(wc)
        ds.WindowWidth  = float(ww)
        ds.SmallestImagePixelValue = smallest
        ds.LargestImagePixelValue  = largest

    # PixelData
    if samples_per_pixel == 1:
        ds.PixelData = arr.tobytes(order="C")
    else:
        arr = arr[:, :, :3].copy(order="C")
        ds.PixelData = arr.tobytes(order="C")
        ds.PlanarConfiguration = 0  # RGBRGB…

    # Save
    study_dir = base_out / study_uid / series_uid
    ensure_directory_exists(str(study_dir))
    out_path = study_dir / f"{sop_uid}.dcm"
    ds.is_little_endian = True
    ds.is_implicit_VR   = False
    ds.save_as(str(out_path), write_like_original=False)
    return str(out_path), study_uid, series_uid, sop_uid


# ---------- route ----------


async def ingest_mime_uploads(
    request: Request,
    files: List[UploadFile],
    session: AsyncSession,
    output_dir: str | None = None,
    wrap_non_dicom: bool = False,
):
    base_out = Path(output_dir or persistent_output_base)
    ensure_directory_exists(str(base_out))

    all_items: List[Dict[str, Any]] = []
    total_dicom = 0

    for up in files:
        try:
            logger.info(f"[MIME] Processing {up.filename}")
            raw = await up.read()
            try:
                msg = message_from_bytes(raw)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid MIME file: {e}")

            parts = _extract_candidate_parts(msg)
            if not parts:
                boundary_parts = _parse_boundary_only_mime(raw)
                if boundary_parts:
                    extracted_for_this_file: List[Dict[str, Any]] = []
                    for fname, payload, ctype in boundary_parts:
                        try:
                            is_dicom = _is_dicom_bytes(payload) or ("application/dicom" in (ctype or ""))
                            if is_dicom:
                                # Ensure it's an imaging object; otherwise treat as non-DICOM or wrap
                                try:
                                    ds_probe = pydicom.dcmread(io.BytesIO(payload), force=True, stop_before_pixels=True)
                                    imaging = _looks_like_imaging(ds_probe)
                                except Exception:
                                    imaging = False

                                if not imaging:
                                    if wrap_non_dicom and (ctype or "").startswith("image/"):
                                        # Wrap as Secondary Capture to ensure pixels
                                        persistent_path, study_uid, series_uid, sop_uid = _wrap_image_as_sc_dicom(
                                            payload, base_out=base_out
                                        )
                                        total_dicom += 1
                                        ds = pydicom.dcmread(persistent_path, force=True)

                                        headers_for_log = {
                                            "StudyInstanceUID": study_uid,
                                            "SeriesInstanceUID": series_uid,
                                            "SOPInstanceUID": sop_uid,
                                        }

                                        try:
                                            await save_dicom_metadata(headers_for_log, session)
                                            await session.commit()
                                        except SQLAlchemyError as e:
                                            logger.error(f"[DB] Commit failed while saving metadata: {e}")
                                            await session.rollback()

                                        thumb_path = persistent_path.replace(".dcm", "_thumb.jpg")
                                        try:
                                            if hasattr(ds, "PixelData") or hasattr(
                                                ds, "FloatPixelData"
                                            ) or hasattr(ds, "DoubleFloatPixelData"):
                                                await generate_thumbnail(
                                                    ds, Path(thumb_path), study_uid, series_uid, sop_uid, session
                                                )
                                            else:
                                                logger.warning(
                                                    f"[THUMB] skipping; no usable pixel data for SOP {sop_uid}"
                                                )
                                        except Exception as e:
                                            logger.warning(f"[THUMB] failed: {e}")

                                        await _publish_dicom_for_viewing(persistent_path)

                                        try:
                                            await log_conversion(
                                                session=session,
                                                input_file=f"{up.filename}:{fname}",
                                                output_file=persistent_path,
                                                format="dicom(sc-wrap)",
                                                status="success",
                                                study_uid=study_uid,
                                                error="",
                                                metadata_quality="derived",
                                            )
                                        except Exception as e:
                                            logger.warning(f"[LOG] conversion log failed: {e}")

                                        try:
                                            await _log_dicom_metadata_compat(
                                                ds,
                                                session=session,
                                                study_uid=study_uid,
                                                series_uid=series_uid,
                                                sop_uid=sop_uid,
                                                phase="pre",
                                            )
                                            try:
                                                await session.commit()
                                            except Exception:
                                                pass
                                        except Exception as e:
                                            logger.warning(f"[LOG] dicom_metadata (pre) failed: {e}")
                                            try:
                                                await session.rollback()
                                            except Exception:
                                                pass

                                        download_url = await _download_url_for_output(request, session, persistent_path)
                                        ohif_url = build_ohif_url(request, study_uid)
                                        extracted_for_this_file.append(
                                            {
                                                "filename": fname,
                                                "output_file": persistent_path,
                                                "download_url": download_url,
                                                "ohif_url": ohif_url,
                                                "study_uid": study_uid,
                                                "series_uid": series_uid,
                                                "sop_uid": sop_uid,
                                                "metadata": extract_metadata(ds),
                                            }
                                        )
                                        continue
                                    else:
                                        # Save raw to non_dicom rather than making a pixel-less DICOM
                                        non_dicom_dir = base_out / "non_dicom"
                                        non_dicom_dir.mkdir(parents=True, exist_ok=True)
                                        out_path = non_dicom_dir / fname
                                        with open(out_path, "wb") as f:
                                            f.write(payload)
                                        download_url = await _download_url_for_output(request, session, out_path)
                                        extracted_for_this_file.append(
                                            {
                                                "filename": fname,
                                                "output_file": str(out_path),
                                                "download_url": download_url,
                                                "study_uid": "",
                                                "series_uid": "",
                                                "sop_uid": "",
                                                "metadata": {
                                                    "note": "Non-imaging DICOM or mislabelled binary; saved as-is",
                                                    "content_type": ctype or "unknown",
                                                },
                                            }
                                        )
                                        continue

                                # Imaging → persist normally
                                persistent_path, study_uid, series_uid, sop_uid = _persist_dicom_bytes(
                                    payload, base_out=base_out
                                )
                                total_dicom += 1
                                ds = pydicom.dcmread(persistent_path, force=True)

                                headers_for_log = {
                                    "StudyInstanceUID": study_uid,
                                    "SeriesInstanceUID": series_uid,
                                    "SOPInstanceUID": sop_uid,
                                }

                                try:
                                    await save_dicom_metadata(headers_for_log, session)
                                    await session.commit()
                                except SQLAlchemyError as e:
                                    logger.error(f"[DB] Commit failed while saving metadata: {e}")
                                    await session.rollback()

                                thumb_path = persistent_path.replace(".dcm", "_thumb.jpg")
                                try:
                                    if hasattr(ds, "PixelData") or hasattr(ds, "FloatPixelData") or hasattr(
                                        ds, "DoubleFloatPixelData"
                                    ):
                                        await generate_thumbnail(
                                            ds, Path(thumb_path), study_uid, series_uid, sop_uid, session
                                        )
                                    else:
                                        logger.warning(f"[THUMB] skipping; no usable pixel data for SOP {sop_uid}")
                                except Exception as e:
                                    logger.warning(f"[THUMB] failed: {e}")

                                await _publish_dicom_for_viewing(persistent_path)

                                try:
                                    await log_conversion(
                                        session=session,
                                        input_file=f"{up.filename}:{fname}",
                                        output_file=persistent_path,
                                        format="dicom",
                                        status="success",
                                        study_uid=study_uid,
                                        error="",
                                        metadata_quality="complete",
                                    )
                                except Exception as e:
                                    logger.warning(f"[LOG] conversion log failed: {e}")

                                try:
                                    await _log_dicom_metadata_compat(
                                        ds,
                                        session=session,
                                        study_uid=study_uid,
                                        series_uid=series_uid,
                                        sop_uid=sop_uid,
                                        phase="pre",
                                    )
                                    try:
                                        await session.commit()
                                    except Exception:
                                        pass
                                except Exception as e:
                                    logger.warning(f"[LOG] dicom_metadata (pre) failed: {e}")
                                    try:
                                        await session.rollback()
                                    except Exception:
                                        pass

                                download_url = await _download_url_for_output(request, session, persistent_path)
                                ohif_url = build_ohif_url(request, study_uid)
                                extracted_for_this_file.append(
                                    {
                                        "filename": fname,
                                        "output_file": persistent_path,
                                        "download_url": download_url,
                                        "ohif_url": ohif_url,
                                        "study_uid": study_uid,
                                        "series_uid": series_uid,
                                        "sop_uid": sop_uid,
                                        "metadata": extract_metadata(ds),
                                    }
                                )

                            else:
                                if wrap_non_dicom:
                                    try:
                                        persistent_path, study_uid, series_uid, sop_uid = _wrap_image_as_sc_dicom(
                                            payload, base_out=base_out
                                        )
                                        total_dicom += 1
                                        ds = pydicom.dcmread(persistent_path, force=True)

                                        headers_for_log = {
                                            "StudyInstanceUID": study_uid,
                                            "SeriesInstanceUID": series_uid,
                                            "SOPInstanceUID": sop_uid,
                                        }

                                        try:
                                            await save_dicom_metadata(headers_for_log, session)
                                            await session.commit()
                                        except SQLAlchemyError as e:
                                            logger.error(f"[DB] Commit failed while saving metadata: {e}")
                                            await session.rollback()

                                        thumb_path = persistent_path.replace(".dcm", "_thumb.jpg")
                                        try:
                                            if hasattr(ds, "PixelData") or hasattr(
                                                ds, "FloatPixelData"
                                            ) or hasattr(ds, "DoubleFloatPixelData"):
                                                await generate_thumbnail(
                                                    ds, Path(thumb_path), study_uid, series_uid, sop_uid, session
                                                )
                                            else:
                                                logger.warning(
                                                    f"[THUMB] skipping; no usable pixel data for SOP {sop_uid}"
                                                )
                                        except Exception as e:
                                            logger.warning(f"[THUMB] failed: {e}")

                                        await _publish_dicom_for_viewing(persistent_path)

                                        try:
                                            await log_conversion(
                                                session=session,
                                                input_file=f"{up.filename}:{fname}",
                                                output_file=persistent_path,
                                                format="dicom(sc-wrap)",
                                                status="success",
                                                study_uid=study_uid,
                                                error="",
                                                metadata_quality="derived",
                                            )
                                        except Exception as e:
                                            logger.warning(f"[LOG] conversion log failed: {e}")

                                        try:
                                            await _log_dicom_metadata_compat(
                                                ds,
                                                session=session,
                                                study_uid=study_uid,
                                                series_uid=series_uid,
                                                sop_uid=sop_uid,
                                                phase="pre",
                                            )
                                            try:
                                                await session.commit()
                                            except Exception:
                                                pass
                                        except Exception as e:
                                            logger.warning(f"[LOG] dicom_metadata (pre) failed: {e}")
                                            try:
                                                await session.rollback()
                                            except Exception:
                                                pass

                                        download_url = await _download_url_for_output(request, session, persistent_path)
                                        ohif_url = build_ohif_url(request, study_uid)
                                        extracted_for_this_file.append(
                                            {
                                                "filename": fname,
                                                "output_file": persistent_path,
                                                "download_url": download_url,
                                                "ohif_url": ohif_url,
                                                "study_uid": study_uid,
                                                "series_uid": series_uid,
                                                "sop_uid": sop_uid,
                                                "metadata": extract_metadata(ds),
                                            }
                                        )
                                        continue
                                    except Exception as wrap_e:
                                        logger.warning(f"[WRAP] Failed to wrap non-DICOM image as SC: {wrap_e}")

                                # Save as non-DICOM (no wrap)
                                non_dicom_dir = base_out / "non_dicom"
                                non_dicom_dir.mkdir(parents=True, exist_ok=True)
                                out_path = non_dicom_dir / fname
                                with open(out_path, "wb") as f:
                                    f.write(payload)
                                download_url = await _download_url_for_output(request, session, out_path)
                                extracted_for_this_file.append(
                                    {
                                        "filename": fname,
                                        "output_file": str(out_path),
                                        "download_url": download_url,
                                        "study_uid": "",
                                        "series_uid": "",
                                        "sop_uid": "",
                                        "metadata": {
                                            "note": "Non-DICOM attachment extracted from MIME",
                                            "content_type": ctype or "unknown",
                                        },
                                    }
                                )
                        except Exception as part_err:
                            # Log per-part failure but continue with other parts
                            logger.exception(f"[MIME] Skipped one part due to error: {part_err}")

                    all_items.append(
                        {
                            "original_filename": up.filename,
                            "items": extracted_for_this_file,
                        }
                    )
                    continue
                else:
                    logger.warning(f"[MIME] No extractable parts found in {up.filename}")
                    all_items.append(
                        {
                            "original_filename": up.filename,
                            "items": [],
                            "warning": "No DICOM attachments found.",
                        }
                    )
                    continue

            # Standard DICOM parts (normal path)
            extracted_for_this_file: List[Dict[str, Any]] = []
            for fname, payload in parts:
                try:
                    # Ensure it is imaging before persisting as DICOM
                    try:
                        ds_probe = pydicom.dcmread(io.BytesIO(payload), force=True, stop_before_pixels=True)
                        imaging = _looks_like_imaging(ds_probe)
                    except Exception:
                        imaging = False

                    if not imaging:
                        if wrap_non_dicom:
                            persistent_path, study_uid, series_uid, sop_uid = _wrap_image_as_sc_dicom(
                                payload, base_out=base_out
                            )
                            total_dicom += 1
                            ds = pydicom.dcmread(persistent_path, force=True)

                            headers_for_log = {
                                "StudyInstanceUID": study_uid,
                                "SeriesInstanceUID": series_uid,
                                "SOPInstanceUID": sop_uid,
                            }

                            try:
                                await save_dicom_metadata(headers_for_log, session)
                                await session.commit()
                            except SQLAlchemyError as e:
                                logger.error(f"[DB] Commit failed while saving metadata: {e}")
                                await session.rollback()

                            thumb_path = persistent_path.replace(".dcm", "_thumb.jpg")
                            try:
                                if hasattr(ds, "PixelData") or hasattr(ds, "FloatPixelData") or hasattr(
                                    ds, "DoubleFloatPixelData"
                                ):
                                    await generate_thumbnail(
                                        ds, Path(thumb_path), study_uid, series_uid, sop_uid, session
                                    )
                                else:
                                    logger.warning(f"[THUMB] skipping; no usable pixel data for SOP {sop_uid}")
                            except Exception as e:
                                logger.warning(f"[THUMB] failed: {e}")

                            await _publish_dicom_for_viewing(persistent_path)

                            try:
                                await log_conversion(
                                    session=session,
                                    input_file=f"{up.filename}:{fname}",
                                    output_file=persistent_path,
                                    format="dicom(sc-wrap)",
                                    status="success",
                                    study_uid=study_uid,
                                    error="",
                                    metadata_quality="derived",
                                )
                            except Exception as e:
                                logger.warning(f"[LOG] conversion log failed: {e}")

                            try:
                                await _log_dicom_metadata_compat(
                                    ds,
                                    session=session,
                                    study_uid=study_uid,
                                    series_uid=series_uid,
                                    sop_uid=sop_uid,
                                    phase="pre",
                                )
                                try:
                                    await session.commit()
                                except Exception:
                                    pass
                            except Exception as e:
                                logger.warning(f"[LOG] dicom_metadata (pre) failed: {e}")
                                try:
                                    await session.rollback()
                                except Exception:
                                    pass

                            download_url = await _download_url_for_output(request, session, persistent_path)
                            ohif_url = build_ohif_url(request, study_uid)
                            extracted_for_this_file.append(
                                {
                                    "filename": fname,
                                    "output_file": persistent_path,
                                    "download_url": download_url,
                                    "ohif_url": ohif_url,
                                    "study_uid": study_uid,
                                    "series_uid": series_uid,
                                    "sop_uid": sop_uid,
                                    "metadata": extract_metadata(ds),
                                }
                            )
                            continue

                        # Save as non-dicom (no wrap)
                        non_dicom_dir = base_out / "non_dicom"
                        non_dicom_dir.mkdir(parents=True, exist_ok=True)
                        out_path = non_dicom_dir / fname
                        with open(out_path, "wb") as f:
                            f.write(payload)
                        download_url = await _download_url_for_output(request, session, out_path)
                        extracted_for_this_file.append(
                            {
                                "filename": fname,
                                "output_file": str(out_path),
                                "download_url": download_url,
                                "study_uid": "",
                                "series_uid": "",
                                "sop_uid": "",
                                "metadata": {"note": "Non-imaging DICOM or mislabelled binary; saved as-is"},
                            }
                        )
                        continue

                    # Imaging → persist normally
                    persistent_path, study_uid, series_uid, sop_uid = _persist_dicom_bytes(
                        payload, base_out=base_out
                    )
                    total_dicom += 1
                    ds = pydicom.dcmread(persistent_path, force=True)

                    headers_for_log = {
                        "StudyInstanceUID": study_uid,
                        "SeriesInstanceUID": series_uid,
                        "SOPInstanceUID": sop_uid,
                    }

                    try:
                        await save_dicom_metadata(headers_for_log, session)
                        await session.commit()
                    except SQLAlchemyError as e:
                        logger.error(f"[DB] Commit failed while saving metadata: {e}")
                        await session.rollback()

                    thumb_path = persistent_path.replace(".dcm", "_thumb.jpg")
                    try:
                        if hasattr(ds, "PixelData") or hasattr(ds, "FloatPixelData") or hasattr(
                            ds, "DoubleFloatPixelData"
                        ):
                            await generate_thumbnail(
                                ds, Path(thumb_path), study_uid, series_uid, sop_uid, session
                            )
                        else:
                            logger.warning(f"[THUMB] skipping; no usable pixel data for SOP {sop_uid}")
                    except Exception as e:
                        logger.warning(f"[THUMB] failed: {e}")

                    await _publish_dicom_for_viewing(persistent_path)

                    try:
                        await log_conversion(
                            session=session,
                            input_file=f"{up.filename}:{fname}",
                            output_file=persistent_path,
                            format="dicom",
                            status="success",
                            study_uid=study_uid,
                            error="",
                            metadata_quality="complete",
                        )
                    except Exception as e:
                        logger.warning(f"[LOG] conversion log failed: {e}")

                    try:
                        await _log_dicom_metadata_compat(
                            ds,
                            session=session,
                            study_uid=study_uid,
                            series_uid=series_uid,
                            sop_uid=sop_uid,
                            phase="pre",
                        )
                        try:
                            await session.commit()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.warning(f"[LOG] dicom_metadata (pre) failed: {e}")
                        try:
                            await session.rollback()
                        except Exception:
                            pass

                    download_url = await _download_url_for_output(request, session, persistent_path)
                    ohif_url = build_ohif_url(request, study_uid)

                    extracted_for_this_file.append(
                        {
                            "filename": fname,
                            "output_file": persistent_path,
                            "download_url": download_url,
                            "ohif_url": ohif_url,
                            "study_uid": study_uid,
                            "series_uid": series_uid,
                            "sop_uid": sop_uid,
                            "metadata": extract_metadata(ds),
                        }
                    )

                except Exception as inner_e:
                    logger.exception(f"[MIME] Failed to process part {fname}: {inner_e}")
                    try:
                        await log_conversion(
                            session=session,
                            input_file=f"{up.filename}:{fname}",
                            output_file="",
                            format="dicom",
                            status="error",
                            study_uid="",
                            error=str(inner_e),
                            metadata_quality="n/a",
                        )
                    except Exception:
                        pass

            all_items.append(
                {
                    "original_filename": up.filename,
                    "items": extracted_for_this_file,
                }
            )

        except Exception as e:
            logger.exception(f"[MIME] Error processing {up.filename}: {e}")
            try:
                await log_conversion(
                    session=session,
                    input_file=up.filename,
                    output_file="",
                    format="mime",
                    status="error",
                    study_uid="",
                    error=str(e),
                    metadata_quality="n/a",
                )
            except Exception:
                pass

    return {"status": "ok", "total_dicoms": total_dicom, "files": all_items}
