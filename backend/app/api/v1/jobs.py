from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.domain.jobs import create_job, get_job, list_jobs
from app.domain.jobs.service import serialize_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., min_length=2)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=1000)


@router.post("")
async def enqueue_job(
    body: JobCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    job = await create_job(
        session,
        job_type=body.job_type,
        input_payload=body.input_payload,
        priority=body.priority,
    )
    return serialize_job(job)


@router.get("")
async def get_jobs(
    status: str | None = None,
    job_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    jobs = await list_jobs(session, status=status, job_type=job_type, limit=limit)
    return [serialize_job(job) for job in jobs]


@router.get("/{job_id}")
async def get_job_status(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    job = await get_job(session, job_id)
    return serialize_job(job)
