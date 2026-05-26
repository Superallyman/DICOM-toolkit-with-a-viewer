from fastapi import APIRouter

from app.api.v1 import (
    admin,
    archive,
    auth,
    conversions,
    deid,
    files,
    health,
    jobs,
    mime,
    studies,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(conversions.router)
api_router.include_router(deid.router)
api_router.include_router(files.router)
api_router.include_router(archive.router)
api_router.include_router(admin.router)
api_router.include_router(studies.router)
api_router.include_router(jobs.router)
api_router.include_router(mime.router)
api_router.include_router(mime.sync_router)
