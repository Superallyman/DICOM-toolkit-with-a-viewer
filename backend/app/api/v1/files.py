from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.db.models import ConversionLog
from app.domain.files import resolve_safe_download_path

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/download")
async def download_generated_file(
    file_path: str = Query(..., description="Generated file path"),
):
    safe_path = resolve_safe_download_path(file_path)
    return FileResponse(
        str(safe_path),
        media_type="application/octet-stream",
        filename=safe_path.name,
    )


@router.get("/conversions/recent")
async def recent_conversion_files(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ConversionLog)
        .where(ConversionLog.output_file.is_not(None))
        .order_by(ConversionLog.timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "input_file": row.input_file,
            "format": row.format,
            "status": row.status,
            "study_uid": row.study_uid,
            "created_at": row.timestamp,
            "download_url": f"/v1/files/{row.id}/download",
        }
        for row in rows
    ]


@router.get("/{conversion_id}/download")
async def download_conversion_output(
    conversion_id: int,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(ConversionLog, conversion_id)
    if row is None or not row.output_file:
        raise HTTPException(status_code=404, detail="File record not found")

    safe_path = resolve_safe_download_path(row.output_file)
    return FileResponse(
        str(safe_path),
        media_type="application/octet-stream",
        filename=safe_path.name,
    )
