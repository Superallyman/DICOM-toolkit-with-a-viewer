from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
import pydicom
from pydicom.pixel_data_handlers.util import apply_voi_lut

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ThumbnailMetadata

log = logging.getLogger(__name__)


async def save_thumbnail_metadata(
    session: AsyncSession,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    path: str,
) -> Optional[ThumbnailMetadata]:
    """
    Upsert a thumbnail metadata row keyed by SOP UID.
    """
    try:
        result = await session.execute(
            select(ThumbnailMetadata).where(ThumbnailMetadata.sop_uid == sop_uid)
        )
        row = result.scalar_one_or_none()

        if row:
            changed = False
            if row.study_uid != study_uid:
                row.study_uid = study_uid
                changed = True
            if row.series_uid != series_uid:
                row.series_uid = series_uid
                changed = True
            if row.path != path:
                row.path = path
                changed = True

            if changed:
                await session.flush()
                await session.commit()
                log.info("🗂️ Updated thumbnail metadata in DB: %s", path)
            else:
                log.debug("Thumbnail metadata already up-to-date for SOP %s", sop_uid)
            return row

        new_record = ThumbnailMetadata(
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            path=path,
        )
        session.add(new_record)
        await session.flush()
        await session.commit()
        log.info("🗂️ Saved thumbnail metadata to DB: %s", path)
        return new_record

    except SQLAlchemyError as e:
        await session.rollback()
        log.exception("❌ DB insert/update failed for thumbnail metadata: %s", e)
        return None


def _normalize_pixel_array(ds: pydicom.Dataset) -> Optional[np.ndarray]:
    """
    Best-effort conversion of DICOM pixels to an 8-bit numpy array suitable for PIL.
    Handles VOI LUT, MONOCHROME1 inversion, multi-frame, and planar config.
    """
    try:
        arr = ds.pixel_array  # may raise if no pixels/unsupported transfer syntax
    except Exception as e:
        log.warning("No pixel data or unsupported syntax for SOP %s: %s", getattr(ds, "SOPInstanceUID", "?"), e)
        return None

    # Apply VOI LUT when present (improves window/level)
    try:
        arr = apply_voi_lut(arr, ds)
    except Exception:
        pass

    # Take first frame if multi-frame
    if arr.ndim == 3 and getattr(ds, "SamplesPerPixel", 1) == 1:
        # Likely (frames, rows, cols)
        arr = arr[0]

    # MONOCHROME1 should be inverted
    if getattr(ds, "PhotometricInterpretation", "").upper() == "MONOCHROME1":
        try:
            arr = arr.max() - arr
        except Exception:
            pass

    # Handle planar configuration for color images
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and getattr(ds, "PlanarConfiguration", 0) == 1:
        # (Samples, Rows, Cols) -> (Rows, Cols, Samples)
        arr = np.transpose(arr, (1, 2, 0))

    # Normalize to 0..255 uint8
    arr = arr.astype(np.float32)
    arr -= arr.min()
    maxv = arr.max()
    if maxv > 0:
        arr /= maxv
    arr = (arr * 255.0).astype(np.uint8)

    # If it has a singleton channel dimension, squeeze it
    if arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[:, :, 0]

    # If still 3D and not RGB, take the first frame safely
    if arr.ndim == 3 and arr.shape[-1] not in (3, 4):
        arr = arr[..., 0]

    return arr


async def generate_thumbnail(
    ds: pydicom.Dataset,
    out_path: Path,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    session: AsyncSession,
    max_size: int = 512,
    quality: int = 85,
) -> Optional[str]:
    """
    Create a JPEG thumbnail for a DICOM dataset and persist a DB record.
    Returns the output path (string) on success, or None on failure.

    This is async to match call sites, but performs CPU work synchronously.
    """
    try:
        arr = _normalize_pixel_array(ds)
        if arr is None:
            log.warning("Skipping thumbnail; no usable pixel data for SOP %s", sop_uid)
            return None

        # Convert to PIL image
        try:
            if arr.ndim == 2:
                img = Image.fromarray(arr, mode="L")
            elif arr.ndim == 3 and arr.shape[-1] == 3:
                img = Image.fromarray(arr, mode="RGB")
            elif arr.ndim == 3 and arr.shape[-1] == 4:
                img = Image.fromarray(arr, mode="RGBA").convert("RGB")
            else:
                # Fallback to grayscale
                img = Image.fromarray(arr if arr.ndim == 2 else arr[..., 0], mode="L")
        except Exception as e:
            log.exception("Failed to create PIL image for SOP %s: %s", sop_uid, e)
            return None

        # Resize while preserving aspect ratio
        try:
            img.thumbnail((max_size, max_size))
        except Exception:
            pass

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="JPEG", quality=quality)

        # Upsert metadata row
        await save_thumbnail_metadata(
            session=session,
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            path=str(out_path),
        )

        log.info("🖼️  Thumbnail created at: %s", out_path)
        return str(out_path)

    except Exception as e:
        log.exception("Failed generating thumbnail for SOP %s: %s", sop_uid, e)
        return None
