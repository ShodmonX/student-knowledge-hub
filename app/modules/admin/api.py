from fastapi import APIRouter

from app.modules.admin import backups_api, catalog_api, reports_api, users_api

router = APIRouter()
for module_router in (catalog_api.router, users_api.router, reports_api.router, backups_api.router):
    router.routes.extend(module_router.routes)

__all__ = ["router"]
