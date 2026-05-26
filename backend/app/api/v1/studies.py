from fastapi import APIRouter, Query

from app.domain.studies import list_studies

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("")
async def get_studies(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    patient_id: str | None = Query(None, alias="PatientID"),
    study_date: str | None = Query(None, alias="StudyDate"),
    modality: str | None = Query(None, alias="Modality"),
):
    return await list_studies(
        limit=limit,
        offset=offset,
        patient_id=patient_id,
        study_date=study_date,
        modality=modality,
    )
