from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.domain.deid import anonymize_dicom_upload
from app.utilities.url_helpers import public_api_v1_base_url

router = APIRouter(prefix="/deid", tags=["deid"])


@router.post("/anonymize")
async def anonymize_dicom(
    request: Request,
    file: UploadFile = File(...),
    delete_private_tags: bool = Form(True),
    rules_json: str | None = Form(None),
    output_dir: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    import tempfile

    return await anonymize_dicom_upload(
        file=file,
        delete_private_tags=delete_private_tags,
        rules_json=rules_json,
        output_dir=output_dir or tempfile.mkdtemp(),
        download_base_url=public_api_v1_base_url(request),
        session=session,
    )
