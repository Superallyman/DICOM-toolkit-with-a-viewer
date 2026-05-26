# config/database_config.py

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()  # Load environment variables from .env

class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dicom_admin:pass123@localhost:5432/dicomdb"
    )

settings = Settings()

# ✅ Export this for Alembic
DATABASE_URL = settings.database_url

