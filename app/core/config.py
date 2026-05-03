import json
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Student Knowledge Hub API"
    app_env: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    api_v1_prefix: str = "/api/v1"

    db_url: str = "sqlite+aiosqlite:///./student_knowledge_hub.db"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    default_page_size: int = 20
    max_page_size: int = 100

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_statement_timeout_ms: int | None = 30_000

    rate_limit_enabled: bool = True
    rate_limit_key_prefix: str = "skh"
    rate_limit_in_memory_fallback: bool = True
    rate_limit_login_max_requests: int = 10
    rate_limit_login_window_seconds: int = 60
    rate_limit_register_max_requests: int = 5
    rate_limit_register_window_seconds: int = 300
    rate_limit_password_reset_request_max_requests: int = 5
    rate_limit_password_reset_request_window_seconds: int = 3600
    rate_limit_password_reset_confirm_max_requests: int = 10
    rate_limit_password_reset_confirm_window_seconds: int = 300
    rate_limit_refresh_max_requests: int = 30
    rate_limit_refresh_window_seconds: int = 60
    rate_limit_sensitive_max_requests: int = 20
    rate_limit_sensitive_window_seconds: int = 60
    login_lockout_max_attempts: int = 5
    login_lockout_window_seconds: int = 900
    login_lockout_seconds: int = 900
    access_token_revocation_enabled: bool = True

    upload_max_file_size: int = 10 * 1024 * 1024
    upload_max_total_size: int = 50 * 1024 * 1024
    upload_max_file_count: int = 10

    storage_backend: Literal["local", "s3"] = "local"
    storage_root: str = "./storage"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_presigned_expiry_seconds: int = 300
    backup_local_root: str = "./backups"
    backup_filename_prefix: str = "student-knowledge-hub"
    backup_timeout_seconds: int = 600
    backup_verify_restore: bool = True
    backup_retention_local: int = 7
    backup_offsite_enabled: bool = False
    backup_retention_offsite: int = 14
    backup_s3_prefix: str = "production/postgres"
    backup_max_restore_size_bytes: int = 5 * 1024 * 1024 * 1024
    backup_restore_confirmation_required: bool = True
    backup_restore_api_enabled: bool = False
    backup_schedule_enabled: bool = False
    backup_interval_seconds: int = 24 * 60 * 60
    backup_run_on_start: bool = True
    public_web_base_url: str = "http://localhost:3000"
    mail_enabled: bool = False
    mail_host: str = "sandbox.smtp.mailtrap.io"
    mail_port: int = 2525
    mail_username: str | None = None
    mail_password: str | None = None
    mail_api_token: str | None = None
    mail_api_url: str = "https://send.api.mailtrap.io/api/send"
    mail_from_email: str = "no-reply@studentknowledgehub.local"
    mail_from_name: str = "Student Knowledge Hub"
    mail_starttls: bool = True
    mail_timeout_seconds: int = 10
    email_outbox_poll_seconds: int = 10
    email_outbox_batch_size: int = 10
    email_outbox_max_attempts: int = 5
    email_outbox_retry_base_seconds: int = 60
    email_verification_token_expire_hours: int = 24
    password_reset_url_path: str = "/reset-password"
    email_verification_url_path: str = "/verify-email"
    telegram_bot_username: str | None = None
    telegram_link_session_ttl_seconds: int = 600
    backend_service_name: str = "backend-api"
    bot_service_name: str = "telegram-bot"
    internal_auth_secret: str | None = None
    internal_auth_ttl_seconds: int = 300
    telegram_event_push_enabled: bool = False
    bot_internal_base_url: str | None = None
    bot_internal_event_path: str = "/internal/events"
    bot_internal_timeout_seconds: int = 10
    telegram_event_poll_seconds: int = 10
    telegram_event_batch_size: int = 50
    telegram_event_max_attempts: int = 5
    redis_url: str | None = None
    redis_password: str | None = None
    cache_ttl_stats_seconds: int = 300
    cache_ttl_trending_seconds: int = 300
    pilot_university_required: bool = True

    admin_email: str = "admin@example.com"
    admin_password: str = "admin123456"
    admin_full_name: str = "Platform Admin"

    @property
    def is_production(self) -> bool:
        return self.app_env in {"prod", "production"}

    @property
    def alembic_sync_url(self) -> str:
        return self.db_url.replace("asyncpg", "psycopg")

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"prod", "production"}:
                return "production"
            if normalized in {"dev", "development"}:
                return "development"
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "0", "false", "no"}:
                return False
            if normalized in {"dev", "development", "1", "true", "yes"}:
                return True
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def normalize_cors_origins(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("storage_backend", mode="before")
    @classmethod
    def normalize_storage_backend(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"spaces", "digitalocean-spaces", "do-spaces"}:
                return "s3"
            return normalized
        return value

    @field_validator("s3_endpoint_url", mode="before")
    @classmethod
    def normalize_s3_endpoint_url(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator(
        "s3_bucket",
        "s3_region",
        "s3_access_key_id",
        "s3_secret_access_key",
        "backup_s3_prefix",
        "mail_username",
        "mail_password",
        "mail_api_token",
        "internal_auth_secret",
        "bot_internal_base_url",
        "redis_password",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_runtime_safety(self):
        if not self.is_production:
            return self

        issues: list[str] = []
        if self.debug:
            issues.append("DEBUG must be false in production")
        if self.jwt_secret_key == "change-me":
            issues.append("JWT_SECRET_KEY must be changed in production")
        if self.admin_email == "admin@example.com":
            issues.append("ADMIN_EMAIL must be changed in production")
        if self.admin_password == "admin123456":
            issues.append("ADMIN_PASSWORD must be changed in production")
        if not self.cors_origins:
            issues.append("CORS_ORIGINS must not be empty in production")
        if (
            self.rate_limit_enabled or self.access_token_revocation_enabled
        ) and not self.redis_url:
            issues.append(
                "REDIS_URL is required in production for rate limiting and token revocation"
            )
        if self.redis_url and urlparse(self.redis_url).password is None:
            issues.append("REDIS_URL must include a Redis password in production")
        if self.mail_enabled:
            has_api_credentials = bool(self.mail_api_token)
            has_smtp_credentials = bool(self.mail_username and self.mail_password)
            if not has_api_credentials and not has_smtp_credentials:
                issues.append(
                    "Mail delivery is enabled but missing MAIL_API_TOKEN or "
                    "MAIL_USERNAME/MAIL_PASSWORD"
                )
            if not self.mail_from_email:
                issues.append("Mail delivery is enabled but missing MAIL_FROM_EMAIL")
        if self.telegram_event_push_enabled:
            if not self.internal_auth_secret:
                issues.append("Telegram event push is enabled but missing INTERNAL_AUTH_SECRET")
            if not self.bot_internal_base_url:
                issues.append("Telegram event push is enabled but missing BOT_INTERNAL_BASE_URL")
        if self.storage_backend == "s3":
            required_s3 = {
                "S3_BUCKET": self.s3_bucket,
                "S3_REGION": self.s3_region,
                "S3_ENDPOINT_URL": self.s3_endpoint_url,
                "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
            }
            missing = [key for key, value in required_s3.items() if not value]
            if missing:
                issues.append(f"S3 storage is enabled but missing: {', '.join(missing)}")

        if issues:
            raise ValueError("; ".join(issues))
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
