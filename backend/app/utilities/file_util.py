# app/utilities/file_utils.py

import os
import shutil
from pathlib import Path
import logging
import pydicom
import hashlib

from app.db.models import UIDPathMapping  # Ensure import matches your project structure
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from config.config import OHIF_VIEWER_DIR, STUDIES_DIR
from app.utilities.shared_utils import decode_pixel_data# Your existing pixel decoder
from pydicom import dcmread
from PIL import Image
from app.utilities.regenerate_uid_map import regenerate_uid_map


def hash_uid(uid: str) -> str:
    """
    Generates a short, filesystem-safe 12-character hash for a DICOM UID using SHA-1.

    Parameters:
    - uid (str): The original DICOM UID.

    Returns:
    - str: A 12-character hexadecimal hash string.
    """
    return hashlib.sha1(uid.encode()).hexdigest()[:12]

"""def copy_dicom_to_ohif(dicom_file_path, study_instance_uid, ohif_viewer_path):
    
    Copies a DICOM file to the OHIF-compatible folder structure using hashed UIDs.

    Path: {OHIF_ROOT}/studies/<hashed_study_uid>/<hashed_series_uid>/<hashed_sop_uid>.dcm
    
    try:
        dicom_file_path = Path(dicom_file_path)

        if not dicom_file_path.exists():
            print(f"❌ DICOM source file does not exist: {dicom_file_path}")
            return

        ds = pydicom.dcmread(dicom_file_path)

        # Fallback-safe values from dataset
        series_uid = getattr(ds, "SeriesInstanceUID", "1.2.3")
        sop_uid = getattr(ds, "SOPInstanceUID", dicom_file_path.stem)

        # ✅ Apply consistent hashing for filesystem-safe folder structure
        hashed_study_uid = hash_uid(study_instance_uid)
        hashed_series_uid = hash_uid(series_uid)
        hashed_sop_uid = hash_uid(sop_uid)

        target_dir = Path(ohif_viewer_path) / "studies" / hashed_study_uid / hashed_series_uid
        target_dir.mkdir(parents=True, exist_ok=True)

        output_path = target_dir / f"{hashed_sop_uid}.dcm"
        shutil.copyfile(dicom_file_path, output_path)

        print(f"✅ Copied to OHIF studies folder: {output_path}")

    except Exception as e:
        print(f"❌ Exception during copy to OHIF folder:\n  Source: {dicom_file_path}\n  Error: {e}")"""


def copy_dicom_to_ohif(dicom_file_path: str, ohif_root: str | None = None):
    """
    Copies a DICOM file and a thumbnail into:
      <OHIF_ROOT>/studies/<StudyHash>/<SeriesHash>/<SOPHash>.dcm(.jpg)
    """
    try:
        src = Path(dicom_file_path)
        if not src.exists():
            logging.error(f"❌ DICOM source file does not exist: {src}")
            return

        ds = dcmread(src)
        study_uid = str(getattr(ds, "StudyInstanceUID", ""))
        series_uid = str(getattr(ds, "SeriesInstanceUID", ""))
        sop_uid = str(getattr(ds, "SOPInstanceUID", ""))

        if not all([study_uid, series_uid, sop_uid]):
            logging.error(f"❌ Missing UID(s) in DICOM file: {src}")
            return

        if ohif_root is None:
            ohif_root = Path(OHIF_VIEWER_DIR)
            ohif_root.mkdir(parents=True, exist_ok=True)

        study_hash = hash_uid(study_uid)
        series_hash = hash_uid(series_uid)
        sop_hash = hash_uid(sop_uid)

        target_dir = Path(ohif_root) / "studies" / study_hash / series_hash
        target_dir.mkdir(parents=True, exist_ok=True)

        target_dcm_path = target_dir / f"{sop_hash}.dcm"
        if src.resolve() == target_dcm_path.resolve():
            logging.info(f"DICOM file already available in OHIF studies folder: {target_dcm_path}")
            return

        shutil.copyfile(src, target_dcm_path)
        logging.info(f"✅ Copied DICOM file to: {target_dcm_path}")

        # Optional: regenerate map if you actually use it elsewhere.
        try:
            regenerate_uid_map()
        except Exception as e:
            logging.debug(f"UID map regeneration skipped/failed: {e}")

        # Thumbnail
        try:
            px = decode_pixel_data(ds)
            img = px if isinstance(px, Image.Image) else Image.fromarray(px).convert("L")
            thumb = target_dir / f"{sop_hash}.jpg"
            img.thumbnail((256, 256))
            img.save(thumb, format="JPEG")
            logging.info(f"🖼️  Thumbnail saved: {thumb}")
        except Exception as e:
            logging.warning(f"⚠️ Failed to generate thumbnail: {e}")

    except Exception as e:
        logging.exception(f"❌ Failed to copy to OHIF: {e}")




async def get_dicom_file_path_from_uid(
    session: AsyncSession,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    base_dir: str = "persistent_output",
) -> Path:
    from app.utilities.file_util import hash_uid

    hashed_study = hash_uid(study_uid)
    hashed_series = hash_uid(series_uid)
    hashed_sop = hash_uid(sop_uid)

    candidate_path = Path(base_dir) / "studies" / hashed_study / hashed_series / f"{hashed_sop}.dcm"

    if not candidate_path.exists():
        raise FileNotFoundError(f"DICOM file not found for {study_uid}/{series_uid}/{sop_uid}")
    return candidate_path
