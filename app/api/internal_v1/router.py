from fastapi import APIRouter

from app.modules.telegram import internal_api as telegram

internal_v1_router = APIRouter()
internal_v1_router.include_router(telegram.router, prefix="/telegram", tags=["internal-telegram"])

__all__ = ["internal_v1_router"]
