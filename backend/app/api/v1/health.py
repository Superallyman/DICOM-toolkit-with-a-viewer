from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.db.models import ConversionLog

router = APIRouter(tags=["health"])


@router.get("/healthcheck")
async def health_check():
    return {"status": "ok", "message": "DICOM Toolkit API is healthy"}


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)):
    await session.execute(select(1))
    return {"status": "ok", "dependencies": {"database": "ok"}}


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_session)):
    success_count = await session.scalar(select(func.count()).where(ConversionLog.status == "success"))
    failure_count = await session.scalar(select(func.count()).where(ConversionLog.status == "failed"))
    return {
        "conversion_success": success_count,
        "conversion_failed": failure_count,
    }
