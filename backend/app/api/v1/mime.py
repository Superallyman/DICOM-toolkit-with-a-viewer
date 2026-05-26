from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.domain.mime.ingestion import ingest_mime_uploads
from app.domain.mime.staging import stage_mime_ingest_job
from app.utilities.url_helpers import public_api_base_url

router = APIRouter(prefix="/mime-ingest", tags=["mime-ingest"])
sync_router = APIRouter(prefix="/mime", tags=["mime-ingest"])


@router.post("/jobs")
async def enqueue_mime_ingest(
    request: Request,
    files: list[UploadFile] = File(...),
    wrap_non_dicom: bool = Query(False),
    output_dir: str | None = Query(None),
    priority: int = Query(100, ge=0, le=1000),
    session: AsyncSession = Depends(get_session),
):
    return await stage_mime_ingest_job(
        files=files,
        wrap_non_dicom=wrap_non_dicom,
        output_dir=output_dir,
        base_url=public_api_base_url(request),
        priority=priority,
        session=session,
    )


@sync_router.post("/ingest")
async def ingest_mime(
    request: Request,
    files: list[UploadFile] = File(..., description="One or more .mime/.eml files"),
    session: AsyncSession = Depends(get_session),
    output_dir: str | None = Query(None, description="Optional override for persistent output (debug)"),
    wrap_non_dicom: bool = Query(False, description="If true, wrap image/* parts as Secondary Capture DICOM"),
):
    return await ingest_mime_uploads(
        request=request,
        files=files,
        session=session,
        output_dir=output_dir,
        wrap_non_dicom=wrap_non_dicom,
    )
