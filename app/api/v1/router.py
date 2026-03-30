from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    catalog_proposals,
    comments,
    faculties,
    materials,
    moderation,
    notifications,
    subjects,
    universities,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(catalog_proposals.router, prefix="/catalog-proposals", tags=["catalog-proposals"])
api_router.include_router(universities.router, prefix="/universities", tags=["universities"])
api_router.include_router(faculties.router, prefix="/faculties", tags=["faculties"])
api_router.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
api_router.include_router(materials.router, prefix="/materials", tags=["materials"])
api_router.include_router(comments.router, prefix="/comments", tags=["comments"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(moderation.router, prefix="/moderation", tags=["moderation"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
