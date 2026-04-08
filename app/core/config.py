import json
from functools import lru_cache
from typing import Annotated, Literal

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
    backup_schedule_enabled: bool = False
    backup_interval_seconds: int = 24 * 60 * 60
    backup_run_on_start: bool = True
    public_web_base_url: str = "http://localhost:3000"
    telegram_bot_username: str | None = None
    telegram_link_session_ttl_seconds: int = 600
    internal_service_token: str | None = None
    internal_service_name: str = "telegram-bot"
    internal_service_secret: str | None = None
    internal_request_ttl_seconds: int = 300
    telegram_event_push_enabled: bool = False
    telegram_bot_service_base_url: str | None = None
    telegram_bot_service_event_path: str = "/internal/events"
    telegram_bot_service_name: str = "backend-api"
    telegram_bot_service_secret: str | None = None
    telegram_bot_service_timeout_seconds: int = 10
    redis_url: str | None = None
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
