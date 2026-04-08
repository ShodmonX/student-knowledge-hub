from fastapi import APIRouter

from app.api.internal_v1 import internal_v1_router
from app.api.v1 import v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/v1")
api_router.include_router(internal_v1_router, prefix="/internal/v1")

__all__ = ["api_router"]
