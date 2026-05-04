from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_context_middleware
from app.api.router import api_router
from app.db.session import engine
from app.bootstrap.backup_service import BackupService, BackupError
from app.infrastructure.storage.service import StorageService

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    cache = get_cache()
    await cache.initialize(settings.redis_url)
    yield
    await cache.close()


app = FastAPI(
    title=settings.app_name, 
    debug=settings.debug, 
    lifespan=lifespan,
    openapi_url="/openapi.json" if settings.debug else None,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)
app.middleware("http")(request_context_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str | bool]:
    cache = get_cache()
    return {"status": "ok", "redis_cache": cache.is_redis_enabled}


@app.get("/health/live", tags=["health"])
async def health_live() -> dict[str, str | bool]:
    return await health()


@app.get("/health/ready", tags=["health"])
async def health_ready() -> JSONResponse:
    database = await _database_health()
    storage = await _storage_health()
    cache = _cache_health()
    backups = _backup_health()

    overall_status = "ok"
    status_code = 200
    if database["status"] == "error" or storage["status"] == "error":
        overall_status = "error"
        status_code = 503
    elif cache["status"] == "degraded" or backups["status"] == "degraded":
        overall_status = "degraded"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "environment": settings.app_env,
            "services": {
                "database": database,
                "cache": cache,
                "storage": storage,
                "backups": backups,
            },
        },
    )


async def _database_health() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - branch exercised via API tests
        return {"status": "error", "detail": str(exc)}
    return {"status": "ok"}


def _cache_health() -> dict[str, str | bool]:
    cache = get_cache()
    if cache.is_redis_enabled:
        return {"status": "ok", "backend": "redis", "enabled": True}
    if settings.redis_url:
        return {"status": "degraded", "backend": "redis", "enabled": False}
    return {"status": "disabled", "backend": "none", "enabled": False}


async def _storage_health() -> dict[str, str]:
    try:
        StorageService()
    except Exception as exc:  # pragma: no cover - branch exercised via API tests
        return {"status": "error", "backend": settings.storage_backend, "detail": str(exc)}

    if settings.storage_backend == "local":
        storage_root = Path(settings.storage_root)
        if not storage_root.exists():
            return {"status": "error", "backend": "local", "detail": "Storage root is missing"}
    return {"status": "ok", "backend": settings.storage_backend}


def _backup_health() -> dict[str, str | bool | int | None]:
    try:
        records = BackupService(settings).list_backups()
    except BackupError as exc:
        return {
            "status": "degraded",
            "schedule_enabled": settings.backup_schedule_enabled,
            "detail": str(exc),
            "latest_backup_id": None,
            "latest_backup_at": None,
        }

    latest = records[0].manifest if records else None
    if settings.backup_schedule_enabled and latest is None:
        return {
            "status": "degraded",
            "schedule_enabled": True,
            "detail": "No backups found yet",
            "latest_backup_id": None,
            "latest_backup_at": None,
        }

    return {
        "status": "ok" if latest is not None or not settings.backup_schedule_enabled else "degraded",
        "schedule_enabled": settings.backup_schedule_enabled,
        "retention_local": settings.backup_retention_local,
        "retention_offsite": settings.backup_retention_offsite,
        "latest_backup_id": latest.backup_id if latest else None,
        "latest_backup_at": latest.created_at if latest else None,
    }
