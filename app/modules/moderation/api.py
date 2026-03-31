from fastapi import APIRouter

from app.modules.moderation import catalog_proposals_api, materials_api

router = APIRouter()
for module_router in (materials_api.router, catalog_proposals_api.router):
    router.routes.extend(module_router.routes)

__all__ = ["router"]
