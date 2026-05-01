import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.session import build_engine_options


def test_production_settings_reject_default_runtime_secrets():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be changed in production"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="change-me",
            admin_email="ops@example.com",
            admin_password="custom-admin-password",
            cors_origins="https://frontend.example.com",
        )


def test_production_settings_reject_default_admin_credentials():
    with pytest.raises(ValidationError, match="ADMIN_EMAIL must be changed in production"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="super-secret-value",
            admin_email="admin@example.com",
            admin_password="admin123456",
            cors_origins="https://frontend.example.com",
        )


def test_production_settings_require_s3_configuration_when_enabled():
    with pytest.raises(ValidationError, match="S3 storage is enabled but missing"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="super-secret-value",
            admin_email="ops@example.com",
            admin_password="custom-admin-password",
            cors_origins="https://frontend.example.com",
            storage_backend="s3",
            s3_bucket="bucket-only",
        )


def test_production_settings_require_redis_for_security_controls():
    with pytest.raises(ValidationError, match="REDIS_URL is required in production"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="super-secret-value",
            admin_email="ops@example.com",
            admin_password="custom-admin-password",
            cors_origins="https://frontend.example.com",
            storage_backend="local",
            redis_url=None,
        )


def test_production_settings_require_authenticated_redis_url():
    with pytest.raises(ValidationError, match="REDIS_URL must include a Redis password"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="super-secret-value",
            admin_email="ops@example.com",
            admin_password="custom-admin-password",
            cors_origins="https://frontend.example.com",
            storage_backend="local",
            redis_url="redis://redis:6379/0",
        )


def test_production_settings_allow_hardened_configuration():
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="super-secret-value",
        admin_email="ops@example.com",
        admin_password="custom-admin-password",
        cors_origins="https://frontend.example.com",
        storage_backend="local",
        redis_url="redis://:strong-redis-password@redis:6379/0",
    )

    assert settings.is_production is True
    assert settings.debug is False


def test_asyncpg_engine_options_include_pool_and_statement_timeout():
    settings = Settings(
        _env_file=None,
        db_url="postgresql+asyncpg://user:pass@db:5432/app",
        db_pool_size=7,
        db_max_overflow=11,
        db_pool_timeout=12,
        db_pool_recycle=600,
        db_pool_pre_ping=True,
        db_statement_timeout_ms=45000,
    )

    options = build_engine_options(settings)

    assert options["pool_size"] == 7
    assert options["max_overflow"] == 11
    assert options["pool_timeout"] == 12
    assert options["pool_recycle"] == 600
    assert options["pool_pre_ping"] is True
    assert options["connect_args"]["server_settings"]["statement_timeout"] == "45000"


def test_sqlite_engine_options_skip_pool_specific_settings():
    settings = Settings(_env_file=None, db_url="sqlite+aiosqlite:///./test.db")

    options = build_engine_options(settings)

    assert options == {"future": True, "echo": False}


def test_dockerignore_excludes_local_state_and_secrets():
    dockerignore = open(".dockerignore", encoding="utf-8").read().splitlines()

    assert ".env" in dockerignore
    assert ".git" in dockerignore
    assert ".pytest_cache" in dockerignore
    assert "storage" in dockerignore
