from fastapi import APIRouter

from app.modules.materials import community_api, management_api, public_api

router = APIRouter()
for module_router in (public_api.router, management_api.router, community_api.router):
    router.routes.extend(module_router.routes)

__all__ = ["router"]
