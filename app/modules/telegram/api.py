from fastapi import APIRouter

from app.modules.telegram import public_api

router = APIRouter()
router.routes.extend(public_api.router.routes)

__all__ = ["router"]
