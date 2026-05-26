# app/db/models.py

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    JSON,
    Text,
    Index,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
    pass


class ConversionLog(Base):
    __tablename__ = "conversion_logs"

    id = Column(Integer, primary_key=True, index=True)
    input_file = Column(String, nullable=False)       # original filename
    output_file = Column(String, nullable=True)       # final persisted path
    format = Column(String, nullable=True)            # e.g., jpeg, png, pdf, dicom
    status = Column(String, nullable=False)           # 'success' | 'failed'
    study_uid = Column(String, nullable=True)         # StudyInstanceUID if available
    error = Column(String, nullable=True)             # error message if failed
    dicom_metadata = Column(JSON, nullable=True)      # optional metadata snapshot
    metadata_quality = Column(String, nullable=True)  # 'complete' | 'incomplete' | 'invalid'
    timestamp = Column(DateTime, default=datetime.utcnow)


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    success = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class DICOMMetadataLog(Base):
    """
    Stores selected DICOM header fields per object so AI De-ID audit can scan
    free-text. `phase` allows comparing pre- vs post-anonymization.
    """
    __tablename__ = "dicom_metadata_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_uid = Column(String, index=True, nullable=False)
    sop_uid = Column(String, nullable=True)
    series_uid = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=False)      # dict of tag -> value
    created_at = Column(DateTime, default=datetime.utcnow)
    # "pre" (before anonymize) or "post" (after anonymize).
    phase = Column(String(10), nullable=False, default="post")


# Helpful composite index for common audit queries
Index(
    "idx_dicom_metadata_study_phase",
    DICOMMetadataLog.study_uid,
    DICOMMetadataLog.phase,
)


class UIDPathMapping(Base):
    __tablename__ = "uid_path_mapping"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    study_uid = Column(String)
    series_uid = Column(String)
    sop_uid = Column(String)
    study_hash = Column(String)
    series_hash = Column(String)
    sop_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class ThumbnailMetadata(Base):
    __tablename__ = "thumbnails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_uid = Column(String, nullable=False)
    series_uid = Column(String, nullable=False)
    sop_uid = Column(String, nullable=False)
    path = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    priority = Column(Integer, nullable=False, default=100)
    input_payload = Column(JSON, nullable=False, default=dict)
    result_payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
