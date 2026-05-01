import os
from collections.abc import AsyncGenerator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from psycopg import sql

os.environ["DB_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/student_knowledge_hub_test",
)
os.environ["APP_ENV"] = "testing"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["REDIS_URL"] = ""
os.environ["MAIL_ENABLED"] = "false"
os.environ["MAIL_API_TOKEN"] = ""
os.environ["RATE_LIMIT_IN_MEMORY_FALLBACK"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_ROOT"] = "./test_storage"
os.environ["TELEGRAM_BOT_USERNAME"] = "bilimhub_bot"
os.environ["INTERNAL_SERVICE_NAME"] = "telegram-bot"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-internal-secret"
os.environ["INTERNAL_REQUEST_TTL_SECONDS"] = "300"

from app.core.security_controls import clear_in_memory_security_store
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


def _connection_kwargs(database_url: str, database_name: str) -> dict[str, object]:
    url = make_url(database_url)
    kwargs: dict[str, object] = {
        "dbname": database_name,
        "user": url.username,
        "password": url.password,
        "host": url.host,
        "port": url.port or 5432,
    }
    return {key: value for key, value in kwargs.items() if value is not None}


def _assert_safe_test_database(database_name: str | None) -> str:
    if not database_name or not (
        database_name.endswith("_test") or database_name.startswith("test_")
    ):
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a dedicated test database whose name "
            "starts with 'test_' or ends with '_test'."
        )
    return database_name


def _drop_database(cursor, database_name: str) -> None:
    cursor.execute(
        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
            sql.Identifier(database_name)
        )
    )


@pytest.fixture(scope="session", autouse=True)
def test_database_lifecycle():
    database_url = os.environ["DB_URL"]
    target_database = _assert_safe_test_database(make_url(database_url).database)
    admin_database = "postgres" if target_database != "postgres" else "template1"
    admin_kwargs = _connection_kwargs(database_url, admin_database)

    with psycopg.connect(**admin_kwargs) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            _drop_database(cursor, target_database)
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
            )

    yield

    with psycopg.connect(**admin_kwargs) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            _drop_database(cursor, target_database)


@pytest.fixture(autouse=True)
async def security_store_cleanup():
    await clear_in_memory_security_store()
    yield
    await clear_in_memory_security_store()

@pytest.fixture()
async def session(test_database_lifecycle) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(os.environ["DB_URL"], future=True)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as test_session:
        yield test_session
    await engine.dispose()


@pytest.fixture()
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
