from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models as _models  # noqa: F401
from app.core.config import Settings, get_settings

settings = get_settings()


def build_engine_options(current_settings: Settings | None = None) -> dict[str, Any]:
    current_settings = current_settings or settings
    options: dict[str, Any] = {"future": True, "echo": False}
    if current_settings.db_url.startswith("sqlite"):
        return options

    options.update(
        pool_size=current_settings.db_pool_size,
        max_overflow=current_settings.db_max_overflow,
        pool_timeout=current_settings.db_pool_timeout,
        pool_recycle=current_settings.db_pool_recycle,
        pool_pre_ping=current_settings.db_pool_pre_ping,
    )
    if "asyncpg" in current_settings.db_url and current_settings.db_statement_timeout_ms:
        options["connect_args"] = {
            "server_settings": {
                "statement_timeout": str(current_settings.db_statement_timeout_ms),
            }
        }
    return options


engine = create_async_engine(settings.db_url, **build_engine_options())
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            if session.in_transaction():
                await session.rollback()
            raise
