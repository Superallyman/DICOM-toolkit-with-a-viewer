from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.db.models import ConversionLog
from app.infrastructure.dicom_archive import DicomArchiveClient

router = APIRouter(prefix="/archive", tags=["archive"])


@router.get("/status")
async def archive_status():
    return await DicomArchiveClient().status()


@router.get("/studies")
async def archive_studies(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    patient_id: str | None = Query(None, alias="PatientID"),
    study_date: str | None = Query(None, alias="StudyDate"),
    modality: str | None = Query(None, alias="Modality"),
):
    return await DicomArchiveClient().search_studies(
        limit=limit,
        offset=offset,
        patient_id=patient_id,
        study_date=study_date,
        modality=modality,
    )


@router.post("/republish-conversions")
async def republish_conversion_dicoms(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ConversionLog)
        .where(ConversionLog.output_file.is_not(None))
        .order_by(ConversionLog.timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    client = DicomArchiveClient()
    published = []

    for row in rows:
        output_file = Path(row.output_file or "")
        if output_file.suffix.lower() != ".dcm":
            continue

        store_result = await client.store_file(output_file)
        published.append(
            {
                "conversion_id": row.id,
                "study_uid": row.study_uid,
                "output_file": str(output_file),
                "stored": store_result.stored,
                "status_code": store_result.status_code,
                "detail": store_result.detail,
            }
        )

    return {"count": len(published), "items": published}
