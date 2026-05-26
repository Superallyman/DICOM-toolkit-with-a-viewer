from __future__ import annotations

import os
import io
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image
import pydicom
from pydicom.dataset import FileDataset
from pydicom.pixel_data_handlers.util import apply_voi_lut
from fastapi import UploadFile, HTTPException

# Reuse your existing helper if you want; not strictly required here.
try:
    # optional import – only used for directory creation if present
    from app.utilities.utilities import ensure_directory_exists  # type: ignore
except Exception:  # pragma: no cover
    def ensure_directory_exists(d: str) -> str:
        os.makedirs(d, exist_ok=True)
        return d


def _read_dicom_from_upload(upload: UploadFile) -> FileDataset:
    """
    Read a DICOM dataset from a Starlette UploadFile safely.
    Resets the file pointer before/after to avoid surprising callers.
    """
    fp = upload.file
    try:
        # make sure we start from the beginning
        pos = fp.tell()
    except Exception:
        pos = None

    try:
        try:
            fp.seek(0)
        except Exception:
            pass

        # Some DICOMs are easier to parse from a temp path (transfer syntaxes, etc.)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dcm") as tmp:
            shutil.copyfileobj(fp, tmp)
            tmp_path = tmp.name

        ds: FileDataset = pydicom.dcmread(tmp_path, force=True)
        return ds
    finally:
        # clean up & restore caller state
        try:
            os.unlink(tmp_path)  # type: ignore
        except Exception:
            pass
        if pos is not None:
            try:
                fp.seek(pos)
            except Exception:
                pass


def _dataset_to_uint8_image(ds: FileDataset) -> Tuple[Image.Image, str]:
    """
    Convert a DICOM dataset to a PIL.Image (uint8) and return (image, mode).
    Handles VOI LUT, MONOCHROME1 inversion, multi-frame selection, and normalization.
    """
    try:
        arr = ds.pixel_array  # may raise if handlers are missing
    except Exception as e:
        # Surface the *real* decoding issue to the client so it can be fixed
        raise RuntimeError(
            "Could not decode DICOM pixel data. If the instance is JPEG/J2K/JLS compressed, "
            "make sure your image handlers are installed (e.g. pylibjpeg[all] / gdcm)."
        ) from e

    # VOI LUT (if present)
    try:
        arr = apply_voi_lut(arr, ds)
    except Exception:
        pass

    # Multi-frame → first frame for still export
    if getattr(ds, "NumberOfFrames", None):
        if arr.ndim == 3:
            # (frames, rows, cols) or (rows, cols, frames) depending on handler
            if arr.shape[0] == int(ds.NumberOfFrames):
                arr = arr[0]
            elif arr.shape[-1] == int(ds.NumberOfFrames):
                arr = arr[..., 0]
        elif arr.ndim == 4:
            # (frames, rows, cols, channels)
            arr = arr[0]

    # MONOCHROME1 needs inversion for usual viewing
    photometric = getattr(ds, "PhotometricInterpretation", "").upper()
    if photometric == "MONOCHROME1":
        arr = np.max(arr) - arr

    # Normalize to uint8 range
    if arr.dtype != np.uint8:
        arr = arr.astype(np.float32)
        mn, mx = float(np.min(arr)), float(np.max(arr))
        if mx > mn:
            arr = (arr - mn) / (mx - mn)
        arr = (arr * 255.0).clip(0, 255).astype(np.uint8)

    # Work out a sensible PIL mode
    mode = "L"
    if arr.ndim == 2:
        pil = Image.fromarray(arr, mode="L")
    elif arr.ndim == 3:
        # H x W x C or C x H x W (rare)
        if arr.shape[0] in (3, 4) and arr.shape[2] not in (3, 4):
            # C x H x W → H x W x C
            arr = np.transpose(arr, (1, 2, 0))

        if arr.shape[2] == 3:
            mode = "RGB"
            pil = Image.fromarray(arr, mode="RGB")
        elif arr.shape[2] == 4:
            mode = "RGBA"
            pil = Image.fromarray(arr, mode="RGBA")
        else:
            # Fallback – squeeze to grayscale
            pil = Image.fromarray(arr[..., 0], mode="L")
            mode = "L"
    else:
        # Unexpected shape; squeeze down
        pil = Image.fromarray(np.squeeze(arr).astype(np.uint8), mode="L")
        mode = "L"

    return pil, mode


def dicom_to_format(
    file: UploadFile,
    output_directory: str,
    format: str,
    quality: int = 95,
) -> str:
    """
    Convert a single DICOM UploadFile into the desired format.
    Keeps the previous signature/return shape.

    Returns the output file path.
    """
    fmt = format.lower().strip()
    if fmt not in {"jpeg", "jpg", "png", "tiff", "tif", "pdf"}:
        raise HTTPException(status_code=400, detail=f"Unsupported target format: {format}")

    ensure_directory_exists(output_directory)

    # Build output path (preserve basename)
    in_name = Path(file.filename or "dicom").stem
    ext = "jpg" if fmt in {"jpeg", "jpg"} else ("tiff" if fmt in {"tif", "tiff"} else fmt)
    out_path = str(Path(output_directory) / f"{in_name}.{ext}")

    try:
        ds = _read_dicom_from_upload(file)
        image, mode = _dataset_to_uint8_image(ds)

        if fmt == "pdf":
            # PIL requires RGB for PDF
            if mode != "RGB":
                image = image.convert("RGB")
            image.save(out_path, "PDF", resolution=300.0)
        elif fmt in {"jpeg", "jpg"}:
            if mode == "RGBA":
                image = image.convert("RGB")
            image.save(out_path, "JPEG", quality=int(quality), optimize=True)
        elif fmt in {"png"}:
            image.save(out_path, "PNG", optimize=True)
        elif fmt in {"tif", "tiff"}:
            image.save(out_path, "TIFF")
        else:  # safety
            raise HTTPException(status_code=400, detail=f"Unsupported target format: {format}")

        return out_path

    except HTTPException:
        # bubble up configured errors
        raise
    except Exception as e:
        logging.exception("DICOM → %s conversion failed", format)
        # Reveal the underlying cause so you can fix libs/handlers
        raise HTTPException(
            status_code=500,
            detail=f"Failed to convert DICOM to {format.upper()}: {e}",
        )
