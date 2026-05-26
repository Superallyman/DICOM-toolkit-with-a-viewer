from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessingJob


def serialize_job(job: ProcessingJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "priority": job.priority,
        "input_payload": job.input_payload,
        "result_payload": job.result_payload,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


async def create_job(
    session: AsyncSession,
    *,
    job_type: str,
    input_payload: dict[str, Any],
    priority: int = 100,
) -> ProcessingJob:
    job = ProcessingJob(
        job_type=job_type,
        status="queued",
        priority=priority,
        input_payload=input_payload,
        updated_at=datetime.utcnow(),
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> ProcessingJob:
    job = await session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def list_jobs(
    session: AsyncSession,
    *,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 100,
) -> list[ProcessingJob]:
    query = select(ProcessingJob)
    if status:
        query = query.where(ProcessingJob.status == status)
    if job_type:
        query = query.where(ProcessingJob.job_type == job_type)
    result = await session.execute(query.order_by(ProcessingJob.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def claim_next_job(session: AsyncSession) -> ProcessingJob | None:
    result = await session.execute(
        select(ProcessingJob)
        .where(ProcessingJob.status == "queued")
        .order_by(ProcessingJob.priority.asc(), ProcessingJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalars().first()
    if job is None:
        return None
    await mark_job_running(session, job)
    return job


async def mark_job_running(session: AsyncSession, job: ProcessingJob) -> ProcessingJob:
    now = datetime.utcnow()
    job.status = "running"
    job.started_at = job.started_at or now
    job.updated_at = now
    await session.flush()
    return job


async def mark_job_succeeded(
    session: AsyncSession,
    job: ProcessingJob,
    result_payload: dict[str, Any],
) -> ProcessingJob:
    now = datetime.utcnow()
    job.status = "succeeded"
    job.result_payload = result_payload
    job.completed_at = now
    job.updated_at = now
    await session.flush()
    return job


async def mark_job_failed(session: AsyncSession, job: ProcessingJob, error: str) -> ProcessingJob:
    now = datetime.utcnow()
    job.status = "failed"
    job.error = error
    job.completed_at = now
    job.updated_at = now
    await session.flush()
    return job
