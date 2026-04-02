import pytest
from pydantic import ValidationError

from app.core.config import Settings


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


def test_production_settings_allow_hardened_configuration():
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="super-secret-value",
        admin_email="ops@example.com",
        admin_password="custom-admin-password",
        cors_origins="https://frontend.example.com",
        storage_backend="local",
    )

    assert settings.is_production is True
    assert settings.debug is False
