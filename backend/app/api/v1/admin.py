from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.db.models import EventLog
from app.utilities.endpoint_helpers import infer_study_uid_from_message, lookup_study_uid_from_metadata

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/events")
async def get_event_logs(
    limit: int = Query(100, ge=1, le=2000),
    event_type: Optional[str] = None,
    success: Optional[bool] = None,
    study_uid: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session),
):
    try:
        query = select(EventLog)

        if event_type:
            query = query.where(EventLog.event_type == event_type)
        if success is not None:
            query = query.where(EventLog.success == success)
        if start_date:
            query = query.where(EventLog.timestamp >= start_date)
        if end_date:
            query = query.where(EventLog.timestamp <= end_date)
        if study_uid:
            query = query.where(EventLog.message.ilike(f"%{study_uid}%"))

        result = await session.execute(query.order_by(EventLog.timestamp.desc()).limit(limit))
        events = result.scalars().all()

        payload = []
        for event in events:
            inferred_study_uid = infer_study_uid_from_message(event.message)
            if not inferred_study_uid:
                inferred_study_uid = await lookup_study_uid_from_metadata(session, event.message)

            payload.append(
                {
                    "id": str(getattr(event, "id", "")),
                    "event_type": getattr(event, "event_type", None),
                    "message": getattr(event, "message", None),
                    "success": bool(getattr(event, "success", False)),
                    "timestamp": getattr(event, "timestamp", None),
                    "study_uid": inferred_study_uid,
                }
            )

        return JSONResponse(content=jsonable_encoder(payload))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve event logs")
