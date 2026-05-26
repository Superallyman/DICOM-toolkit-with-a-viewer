from __future__ import annotations
import os
import shutil
import logging
import warnings
import re
from fastapi import UploadFile, HTTPException
from typing import List, Dict, Any
import pydicom
import uuid
from pydicom.dataset import Dataset
from pydicom.pixel_data_handlers.util import apply_voi_lut
import numpy as np
from PIL import Image
import tempfile
#from app.format_converters import normalize_pixel_data
from config.config import general_config
import mimetypes
import json
from app.db.models import DICOMMetadataLog, UIDPathMapping
from app.utilities.file_util import hash_uid  # make sure this exists or define it
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from io import BytesIO
from typing import Optional
from pathlib import Path
import hashlib



from pydicom.pixel_data_handlers.util import apply_voi_lut
from pydicom.dataset import FileDataset
from pathlib import Path

from app.utilities.thumbnail_dao import save_thumbnail_metadata
from app.db.dependencies import get_session  # or wherever you manage DB sessions

from app.utilities.shared_utils import decode_pixel_data




# Suppress Photometric Interpretation warnings
warnings.filterwarnings(
    "ignore",
    message=(
        "The \\(0028,0004\\) 'Photometric Interpretation' value is 'RGB' however "
        "the encoded image's codestream contains a JFIF APP marker which indicates it should be 'YBR_FULL_422'"
    ),
    category=UserWarning,
    module="pydicom"
)



# Use the already-loaded `general_config`
BASE_UID_PREFIX = general_config.get("BASE_UID_PREFIX", "1.2.840.10008.")  # Use directly from the configuration
OUTPUT_DIR = os.getenv("OUTPUT_DIR", tempfile.mkdtemp())  # Dynamic output directory


# Helper Functions

def ensure_directory_exists(directory: str) -> str:
    """
    Ensure that a directory exists, creating it if necessary.
    """
    try:
        os.makedirs(directory, exist_ok=True)
        return directory
    except Exception as e:
        logging.error(f"Error creating directory {directory}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create directory: {str(e)}")


def generate_study_instance_uid() -> str:
    """
    Generate a unique StudyInstanceUID using the configured prefix.
    """
    try:
        unique_id = uuid.uuid4().int >> 64  # Generate a large random number
        return f"{BASE_UID_PREFIX}{unique_id}"
    except Exception as e:
        logging.error(f"Error generating StudyInstanceUID: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate StudyInstanceUID")



def save_file_to_output_dir(upload_file: UploadFile, output_dir: str = None) -> str:
    """
    Save an uploaded file to the specified or default output directory.
    """
    target_dir = ensure_directory_exists(output_dir or OUTPUT_DIR)
    try:
        output_path = os.path.join(target_dir, upload_file.filename)
        with open(output_path, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        logging.info(f"Saved file: {upload_file.filename} to {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Failed to save file {upload_file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")


def extract_metadata(source) -> Dict[str, Any]:
    """
    Extract DICOM metadata using DICOM keywords so OHIF can consume them as JSON.
    Now seeks to the start of UploadFile and restores the pointer on exit.
    """
    try:
        if isinstance(source, UploadFile):
            fp = source.file
            try:
                pos = fp.tell()
            except Exception:
                pos = None
            try:
                fp.seek(0)
            except Exception:
                pass
            ds = pydicom.dcmread(fp, force=True)
            if pos is not None:
                try:
                    fp.seek(pos)
                except Exception:
                    pass
        elif isinstance(source, pydicom.Dataset):
            ds = source
        else:
            raise ValueError("Unsupported source type for metadata extraction")

        excluded_tags = ["PixelData", "WaveformData"]
        metadata: Dict[str, Any] = {}
        for elem in ds.iterall():
            key = elem.keyword or str(elem.tag)
            val = elem.value
            if key in excluded_tags or isinstance(val, (bytes, bytearray)):
                continue
            if isinstance(val, pydicom.dataset.Dataset):
                metadata[key] = extract_nested_metadata(val)
            else:
                metadata[key] = str(val) if val is not None else "Unknown"
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")


def extract_nested_metadata(nested_dataset: pydicom.dataset.Dataset) -> Dict[str, Any]:
    """
    Recursively extract metadata from nested DICOM datasets using DICOM keywords.
    """
    nested_metadata = {}
    for elem in nested_dataset.iterall():
        tag_key = elem.keyword or str(elem.tag)
        tag_value = elem.value

        if isinstance(tag_value, pydicom.dataset.Dataset):
            nested_metadata[tag_key] = extract_nested_metadata(tag_value)
        else:
            nested_metadata[tag_key] = str(tag_value) if tag_value is not None else "Unknown"
    return nested_metadata

    

def embed_dicom_header(dicom: Dataset, header: Dict[str, Any]) -> List[str]:
    """
    Embed custom header fields into a DICOM dataset.
    
    Args:
        dicom (Dataset): The DICOM dataset to modify.
        header (Dict[str, Any]): The header fields to embed into the dataset.
    
    Returns:
        List[str]: A list of fields that failed to be set (if any).
    """
    failed_fields = []
    for key, value in header.items():
        try:
            # Check if the field exists in the DICOM standard
            if not hasattr(dicom, key):
                logging.warning(f"Field '{key}' does not exist in the DICOM dataset.")
                failed_fields.append(key)
                continue

            # Set the field value
            setattr(dicom, key, value)
            logging.info(f"Successfully set field '{key}' with value '{value}'.")
        except Exception as e:
            logging.warning(f"Could not set header field '{key}': {e}")
            failed_fields.append(key)

    if failed_fields:
        logging.warning(f"Failed to set the following DICOM header fields: {failed_fields}")
    return failed_fields

    


def generate_download_url(base_url: str, file_path: str) -> str:
    """
    Generate a download URL for the given file path.
    """
    base_url = str(base_url)  # Convert URL object to string
    return f"{base_url.rstrip('/')}/files/download?file_path={file_path}"




def validate_dicom_headers(dicom_headers: dict):
    """
    Validate DICOM headers against configured rules.
    """
    # Read settings from general_config
    whitelist_tags = general_config.get("dicom_whitelist_tags", "").split(",")
    auto_generated_tags = general_config.get("dicom_auto_generate_tags", "").split(",")
    max_tags = int(general_config.get("dicom_max_tags", 100))
    max_value_length = int(general_config.get("dicom_max_value_length", 256))

    # Validate whitelist
    for tag in dicom_headers.keys():
        if tag not in whitelist_tags:
            raise HTTPException(status_code=400, detail=f"Unsupported DICOM tag: {tag}")

    # Overwrite critical tags
    for tag in auto_generated_tags:
        if tag in dicom_headers:
            dicom_headers[tag] = generate_study_instance_uid()  # Replace with your UID generator

    # Enforce tag count limit
    if len(dicom_headers) > max_tags:
        raise HTTPException(status_code=400, detail=f"Too many DICOM tags provided. Maximum allowed: {max_tags}")

    # Validate tag values
    for key, value in dicom_headers.items():
        if isinstance(value, str):
            if len(value) > max_value_length:
                raise HTTPException(
                    status_code=400,
                    detail=f"Value for {key} exceeds maximum length of {max_value_length}.",
                )
            # Example: Validate StudyDate format
            if key == "StudyDate" and not re.match(r"^\d{8}$", value):
                raise HTTPException(status_code=400, detail="Invalid StudyDate format. Expected YYYYMMDD.")

    return dicom_headers



__all__ = [
    "ensure_directory_exists",
    "generate_study_instance_uid",
    "embed_dicom_header",
    "save_file_to_output_dir",
    "decode_pixel_data",
    "extract_metadata",
    "generate_download_url",
    "validate_dicom_headers",
]


def detect_mime_type_from_extension(filename: str) -> str:
    """
    Guess MIME type from file extension.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"

def detect_mime_type_from_content(file_bytes: bytes) -> str:
    """
    Detect MIME type from file content using basic magic number heuristics.
    """
    if file_bytes.startswith(b'\xff\xd8'):
        return "image/jpeg"
    elif file_bytes.startswith(b'\x89PNG'):
        return "image/png"
    elif file_bytes.startswith(b'%PDF'):
        return "application/pdf"
    elif file_bytes[0:4] == b'\x00\x00\x00\x1c' or b'ftyp' in file_bytes[:12]:
        return "video/mp4"
    elif file_bytes.startswith(b'II') or file_bytes.startswith(b'MM'):
        return "image/tiff"
    else:
        return "application/octet-stream"
    

async def generate_thumbnail(
    ds: FileDataset,
    output_path: Path,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    session: Optional[AsyncSession] = None,
    size=(128, 128),
) -> str:
    """
    Create a thumbnail for a DICOM instance. If no pixel data, skip gracefully.
    """
    try:
        # --- NEW: skip if no pixels ---
        if not _has_pixel_data(ds):
            logging.warning("[THUMB] skipping thumbnail; no Pixel Data for SOP %s", sop_uid)
            return ""

        # Try ds.pixel_array, but don't crash the request if handlers are missing
        try:
            raw = ds.pixel_array
        except Exception as e:
            logging.exception("[THUMB] pixel_array unavailable: %s", e)
            return ""

        try:
            pixel_array = apply_voi_lut(raw, ds)
        except Exception:
            pixel_array = raw  # fall back silently

        if pixel_array.dtype != np.uint8:
            pixel_array = ((pixel_array - np.min(pixel_array)) / np.ptp(pixel_array)) * 255
            pixel_array = pixel_array.astype(np.uint8, copy=False)

        if hasattr(ds, "PhotometricInterpretation") and ds.PhotometricInterpretation in ("RGB", "YBR_FULL", "YBR_FULL_422"):
            image = Image.fromarray(pixel_array, "RGB") if pixel_array.ndim == 3 else Image.fromarray(pixel_array, "L")
        else:
            image = Image.fromarray(pixel_array)

        image.thumbnail(size)

        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

        logging.info("🖼️ Thumbnail saved: %s", output_path)

        if session is not None:
            await save_thumbnail_metadata(session, study_uid, series_uid, sop_uid, str(output_path))

        return str(output_path)

    except Exception as e:
        logging.exception("❌ Failed to generate thumbnail: %s", e)
        return ""




async def log_dicom_metadata(metadata: dict, db: AsyncSession):
    try:
        study_uid = metadata.get("0020000D", {}).get("Value", [None])[0]
        series_uid = metadata.get("0020000E", {}).get("Value", [None])[0]
        sop_uid = metadata.get("00080018", {}).get("Value", [None])[0]

        if not study_uid or not sop_uid:
            return  # Missing critical UIDs, skip logging

        entry = DICOMMetadataLog(
            id=uuid.uuid4(),
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            metadata_json=metadata,
            created_at=datetime.utcnow(),
        )

        db.add(entry)
        await db.commit()

    except Exception as e:
        # You may log this if needed
        print(f"[LogMetadata] Failed to log DICOM metadata: {e}")
        await db.rollback()


async def save_dicom_metadata(metadata: dict, db: AsyncSession):
    study_uid = metadata["StudyInstanceUID"]
    series_uid = metadata["SeriesInstanceUID"]
    sop_uid = metadata["SOPInstanceUID"]

    db.add(DICOMMetadataLog(
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        metadata_json=metadata,
        created_at=datetime.utcnow()
    ))

    db.add(UIDPathMapping(
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        study_hash=hash_uid(study_uid),
        series_hash=hash_uid(series_uid),
        sop_hash=hash_uid(sop_uid),
    ))

    try:
        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        raise e


def resolve_uid_hash(uid_hash: str, uid_type: str) -> str | None:
    """
    Resolve a hashed UID to its original UID using persistent_output/uid_map.json.

    Args:
        uid_hash (str): The hashed UID (e.g., hashed Study/Series/SOPInstanceUID).
        uid_type (str): One of "study", "series", or "instance".

    Returns:
        str | None: The resolved UID if found, otherwise None.
    """
    try:
        uid_map_path = os.path.join("persistent_output", "uid_map.json")
        if not os.path.exists(uid_map_path):
            print(f"[resolve_uid_hash] UID map not found: {uid_map_path}")
            return None

        with open(uid_map_path, "r") as f:
            uid_map = json.load(f)

        for uid, hashes in uid_map.items():
            if uid_type in hashes and hashes[uid_type] == uid_hash:
                return uid

        print(f"[resolve_uid_hash] UID not found for hash {uid_hash} and type {uid_type}")
        return None
    except Exception as e:
        print(f"[resolve_uid_hash] Error resolving UID: {e}")
        return None
    

def regenerate_uid_map(persistent_output_dir: str = "persistent_output"):
    """
    Regenerate the uid_map.json file by scanning the persistent_output directory structure.
    
    This maps original Study/Series/SOP UIDs to their hashed counterparts.
    """
    uid_map = {}

    try:
        studies_dir = os.path.join(persistent_output_dir, "studies")
        if not os.path.isdir(studies_dir):
            logging.warning(f"📁 Studies directory not found: {studies_dir}")
            return

        for study_hash in os.listdir(studies_dir):
            study_path = os.path.join(studies_dir, study_hash)
            if not os.path.isdir(study_path):
                continue

            for series_hash in os.listdir(study_path):
                series_path = os.path.join(study_path, series_hash)
                if not os.path.isdir(series_path):
                    continue

                for sop_file in os.listdir(series_path):
                    if not sop_file.endswith(".dcm"):
                        continue

                    sop_hash = os.path.splitext(sop_file)[0]
                    dicom_path = os.path.join(series_path, sop_file)

                    try:
                        ds = pydicom.dcmread(dicom_path, stop_before_pixels=True, force=True)
                        study_uid = ds.StudyInstanceUID
                        series_uid = ds.SeriesInstanceUID
                        sop_uid = ds.SOPInstanceUID

                        if study_uid not in uid_map:
                            uid_map[study_uid] = {}

                        uid_map[study_uid]["study"] = hash_uid(study_uid)
                        uid_map[study_uid]["series"] = hash_uid(series_uid)
                        uid_map[study_uid]["instance"] = hash_uid(sop_uid)

                    except Exception as e:
                        logging.warning(f"⚠️ Could not read DICOM file: {dicom_path}, Error: {e}")

        # Write the UID map to JSON file
        map_path = os.path.join(persistent_output_dir, "uid_map.json")
        with open(map_path, "w") as f:
            json.dump(uid_map, f, indent=4)

        logging.info(f"✅ UID map regenerated at {map_path}")

    except Exception as e:
        logging.error(f"❌ Failed to regenerate UID map: {e}")

def ensure_directory_exists(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def hash_uid(uid: str) -> str:
    # short, stable path-safe hash used across the app
    return hashlib.sha1(uid.encode("utf-8")).hexdigest()[:12]

def copy_dicom_to_ohif(
    src_path: str | Path,
    ohif_root: str | Path,
    *,
    study_uid: str | None = None,
    series_uid: str | None = None,
    sop_uid: str | None = None,
) -> str:
    """
    Copy a DICOM file into the OHIF static tree:
      <ohif_root>/studies/<hash(study)>/<hash(series)>/<hash(sop)>.dcm

    UIDs are read from the file if not provided.
    Returns the destination path as a string.
    """
    src = Path(src_path)
    root = Path(ohif_root)

    # Allow either /ohif or /ohif/studies to be passed
    studies_dir = root / "studies"
    if root.name == "studies":
        studies_dir = root

    if not (study_uid and series_uid and sop_uid):
        ds = pydicom.dcmread(str(src), stop_before_pixels=True, force=True)
        study_uid = study_uid or getattr(ds, "StudyInstanceUID", None)
        series_uid = series_uid or getattr(ds, "SeriesInstanceUID", None)
        sop_uid = sop_uid or getattr(ds, "SOPInstanceUID", None)

    if not (study_uid and series_uid and sop_uid):
        raise ValueError("Missing UIDs to place file under OHIF 'studies' tree")

    dst = studies_dir / hash_uid(study_uid) / hash_uid(series_uid) / f"{hash_uid(sop_uid)}.dcm"
    ensure_directory_exists(dst.parent)
    shutil.copy2(src, dst)
    return str(dst)

# utilities.py  (near the other helpers/imports)
def _has_pixel_data(ds: FileDataset) -> bool:
    """True if any DICOM pixel element is present."""
    return any(hasattr(ds, attr) for attr in ("PixelData", "FloatPixelData", "DoubleFloatPixelData"))
