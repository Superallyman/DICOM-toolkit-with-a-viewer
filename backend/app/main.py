# app/main.py

import os
import shutil
import tempfile
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the API project root before importing config.
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # <repo>/app -> <repo>
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.utilities.auth_middleware import authentication_middleware
from app.api.v1.router import api_router
from config.config import CORS_ORIGINS, general_config, OHIF_VIEWER_DIR as CFG_OHIF_VIEWER_DIR
from app.utilities.utilities import validate_dicom_headers  # kept for parity
from app import dicomweb_routes
from app.ai.deid import router as deid_router


# --------------------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------------------
app = FastAPI(
    title="DICOM Toolkit API",
    description=(
        "Control-plane API for DICOM conversion, MIME ingest, de-identification, "
        "archive publishing, background jobs, and OHIF viewer launch workflows."
    ),
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Output dir
OUTPUT_DIR = general_config.get("output_dir", tempfile.mkdtemp())
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Logging
log_level = general_config.get("log_level", "INFO").upper()
if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    print(f"Invalid log level '{log_level}' in config.properties. Defaulting to INFO.")
    log_level = "INFO"

log_file_path = os.getenv("LOG_FILE", "dicom_converter.log")
logging.basicConfig(
    filename=log_file_path,
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Initialized logging configuration.")
logging.info(f"Log file path resolved to: {log_file_path}")
logging.info(f"Output Directory: {OUTPUT_DIR}")

# --------------------------------------------------------------------------------------
# OHIF Viewer mount (env-aware + explicit)
#   Priority: runtime env var > config-sourced default
# --------------------------------------------------------------------------------------
effective_ohif_dir_str = os.getenv("OHIF_VIEWER_DIR") or CFG_OHIF_VIEWER_DIR
# Normalize slashes so Windows paths from .env work either way
effective_ohif_dir_str = effective_ohif_dir_str.replace("\\", "/")
ohif_dir = Path(effective_ohif_dir_str).expanduser()

index_file = ohif_dir / "index.html"
logging.info(f"Effective OHIF_VIEWER_DIR: {ohif_dir}")

if index_file.is_file():
    # Serve the prebuilt OHIF app at /v1/viewer
    app.mount("/v1/viewer", StaticFiles(directory=str(ohif_dir), html=True), name="viewer")
    logging.info(f"OHIF Viewer mounted from: {ohif_dir}")
else:
    logging.warning(
        f"OHIF viewer index.html not found. Expected at: {index_file}. Skipping static mount."
    )

# --------------------------------------------------------------------------------------
# Middleware & rate limiter
# --------------------------------------------------------------------------------------
app.middleware("http")(authentication_middleware)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# --------------------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------------------
app.include_router(api_router, prefix="/v1")
app.include_router(dicomweb_routes.router, prefix="/v1")
app.include_router(deid_router)   # has its own prefix

# --------------------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------------------
processing_temp_dir = tempfile.mkdtemp()

@app.on_event("shutdown")
def cleanup_temp_dir():
    try:
        if os.path.exists(processing_temp_dir):
            shutil.rmtree(processing_temp_dir)
            logging.info("Temporary processing directory cleaned up.")
    except Exception as e:
        logging.error(f"Error cleaning up temporary directory: {str(e)}")

@app.on_event("startup")
async def startup_event():
    logging.info("DICOM Toolkit API started.")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("DICOM Toolkit API shutting down.")
