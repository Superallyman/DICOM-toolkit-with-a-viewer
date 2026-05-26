# app/config.py

import configparser
import os
import tempfile
import logging
from pathlib import Path
from typing import Dict


# ---------------------------
# Helpers
# ---------------------------

def _as_list(val: str) -> list[str]:
    """Split a comma list safely and strip empties."""
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def _ensure_dir(p: Path) -> Path:
    """Create a directory if it doesn't exist and return it."""
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Don't fail import-time just because of perms; caller may fix later
        pass
    return p


# ---------------------------
# Config file loaders
# ---------------------------

def load_general_config(config_file: str = "config.properties") -> configparser.SectionProxy:
    """
    Load the general configurations from the `config.properties` file.
    Expect a [DEFAULT] section.
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
    except configparser.MissingSectionHeaderError as e:
        raise RuntimeError(
            "The configuration file is missing a section header. "
            "Please add '[DEFAULT]' or another section header."
        ) from e

    if "DEFAULT" in config:
        # Debug log (safe only when DEFAULT exists)
        try:
            logging.info("Loaded DEFAULT section: %s", dict(config["DEFAULT"]))
        except Exception:
            pass
        return config["DEFAULT"]

    raise RuntimeError("The configuration file is missing the 'DEFAULT' section.")


def load_client_credentials(config_file: str = "config.properties") -> Dict[str, str]:
    """
    Load client credentials from the [CLIENTS] section.
    Returns a dict mapping username -> password.
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
    except configparser.MissingSectionHeaderError as e:
        raise RuntimeError(
            "The configuration file is missing a section header. "
            "Please add '[CLIENTS]' or another section header."
        ) from e

    if "CLIENTS" not in config:
        return {}

    credentials: Dict[str, str] = {}
    clients = config["CLIENTS"]
    for key in clients:
        if key.endswith(".username"):
            client = key[:-9]  # strip '.username'
            username = clients.get(key, "")
            password = clients.get(f"{client}.password", "")
            if username:
                credentials[username] = password
    return credentials


# ---------------------------
# Load config values
# ---------------------------

general_config = load_general_config()

# General settings
RATE_LIMIT = general_config.get("rate_limit", "10/minute")
AUTH_USERNAME = general_config.get("authenticator.username", "admin")
AUTH_PASSWORD = general_config.get("authenticator.password", "password")
SUPPORTED_FORMATS = _as_list(general_config.get("supported_formats", "jpeg,png,pdf,tiff,mp4"))
BASE_UID_PREFIX = general_config.get("BASE_UID_PREFIX", "1.2.840.10008.")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
CORS_ORIGINS = _as_list(
    os.getenv(
        "CORS_ORIGINS",
        general_config.get(
            "cors_origins",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
        ),
    )
)
DICOM_ARCHIVE_ENABLED = os.getenv("DICOM_ARCHIVE_ENABLED", "false").lower() in {"1", "true", "yes"}
DICOM_ARCHIVE_DICOMWEB_URL = os.getenv("DICOM_ARCHIVE_DICOMWEB_URL", "http://orthanc:8042/dicom-web").rstrip("/")
DICOM_ARCHIVE_STOW_URL = os.getenv("DICOM_ARCHIVE_STOW_URL", f"{DICOM_ARCHIVE_DICOMWEB_URL}/studies")
DICOM_ARCHIVE_USERNAME = os.getenv("DICOM_ARCHIVE_USERNAME") or None
DICOM_ARCHIVE_PASSWORD = os.getenv("DICOM_ARCHIVE_PASSWORD") or None

# Output locations
# Temporary processing output (used by some endpoints)
OUTPUT_DIR = general_config.get("output_dir", tempfile.mkdtemp())

# Resolve project root (allow override via env, else two levels up from this file)
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))

# Persistent output (where final DICOMs/derived live)
PERSISTENT_OUTPUT_DIR = str(
    _ensure_dir(
        Path(
            general_config.get(
                "persistent_output_dir",
                str(PROJECT_ROOT / "persistent_output")
            )
        )
    ).resolve()
)

# DICOM rules
DICOM_WHITELIST_TAGS = _as_list(general_config.get("dicom_whitelist_tags", ""))
DICOM_AUTO_GENERATE_TAGS = _as_list(general_config.get("dicom_auto_generate_tags", ""))
DICOM_MAX_TAGS = int(general_config.get("dicom_max_tags", 100))
DICOM_MAX_VALUE_LENGTH = int(general_config.get("dicom_max_value_length", 256))

# Client auth map
CLIENT_CREDENTIALS = load_client_credentials()

# ---------------------------
# OHIF viewer paths (robust)
# ---------------------------

# Try env first; then common local folders; then Docker default.
_env_ohif = os.getenv("OHIF_VIEWER_DIR")
if _env_ohif and Path(_env_ohif).exists():
    _ohif_dir = Path(_env_ohif)
elif (PROJECT_ROOT / "ohif-dist").exists():
    _ohif_dir = PROJECT_ROOT / "ohif-dist"
elif (PROJECT_ROOT / "ohif" / "dist").exists():
    _ohif_dir = PROJECT_ROOT / "ohif" / "dist"
else:
    # Container default (bind-mount this path to a built OHIF dist)
    _ohif_dir = Path("/app/ohif/dist")

OHIF_VIEWER_DIR = str(_ohif_dir.resolve())

# Where OHIF reads studies if you copy/organize them under the viewer
STUDIES_DIR = Path(OHIF_VIEWER_DIR) / "studies"

# Map of UID -> path hashes (if you use it)
UID_MAP_PATH = str(Path(PERSISTENT_OUTPUT_DIR) / "uid_map.json")

# Ensure useful directories exist (best-effort)
_ensure_dir(Path(PERSISTENT_OUTPUT_DIR))
_ensure_dir(STUDIES_DIR)

# ---------------------------
# Import-time debug output
# ---------------------------

try:
    print("=" * 60)
    print("PATH CONFIGURATION DEBUG:")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"PERSISTENT_OUTPUT_DIR: {PERSISTENT_OUTPUT_DIR}")
    print(f"OHIF_VIEWER_DIR: {OHIF_VIEWER_DIR}")
    print(f"STUDIES_DIR: {STUDIES_DIR}")
    print()

    print("DIRECTORY EXISTENCE CHECK:")
    print(f"PERSISTENT_OUTPUT_DIR exists: {Path(PERSISTENT_OUTPUT_DIR).exists()}")
    print(f"OHIF_VIEWER_DIR exists: {Path(OHIF_VIEWER_DIR).exists()}")
    print(f"STUDIES_DIR exists: {STUDIES_DIR.exists()}")
    print(f"OHIF index.html exists: {(Path(OHIF_VIEWER_DIR) / 'index.html').is_file()}")

    # Show what is under the persistent 'studies' root (not necessarily OHIF dir)
    studies_persistent_dir = Path(PERSISTENT_OUTPUT_DIR) / "studies"
    print(f"Persistent studies dir exists: {studies_persistent_dir.exists()}")

    if studies_persistent_dir.exists():
        try:
            study_folders = [d.name for d in studies_persistent_dir.iterdir() if d.is_dir()]
            print(f"Number of study folders found: {len(study_folders)}")
            if study_folders:
                print(f"Sample study folders: {study_folders[:3]}")
        except Exception as e:
            print(f"Error reading studies directory: {e}")
    print("=" * 60)
except Exception:
    # Never fail app import just because of debug printing
    pass
