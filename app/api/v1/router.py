from fastapi import APIRouter

from app.modules.admin import api as admin
from app.modules.auth import api as auth
from app.modules.catalog import faculties_api as faculties
from app.modules.catalog import subjects_api as subjects
from app.modules.catalog import universities_api as universities
from app.modules.catalog_proposals import api as catalog_proposals
from app.modules.community import api as comments
from app.modules.materials import api as materials
from app.modules.moderation import api as moderation
from app.modules.notifications import api as notifications
from app.modules.tags import api as tags
from app.modules.users import api as users
from app.modules.telegram import api as telegram

v1_router = APIRouter()
v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
v1_router.include_router(users.router, prefix="/users", tags=["users"])
v1_router.include_router(telegram.router, tags=["telegram"])
v1_router.include_router(catalog_proposals.router, prefix="/catalog-proposals", tags=["catalog-proposals"])
v1_router.include_router(universities.router, prefix="/universities", tags=["universities"])
v1_router.include_router(faculties.router, prefix="/faculties", tags=["faculties"])
v1_router.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
v1_router.include_router(tags.router, prefix="/tags", tags=["tags"])
v1_router.include_router(materials.router, prefix="/materials", tags=["materials"])
v1_router.include_router(comments.router, prefix="/comments", tags=["comments"])
v1_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
v1_router.include_router(moderation.router, prefix="/moderation", tags=["moderation"])
v1_router.include_router(admin.router, prefix="/admin", tags=["admin"])
