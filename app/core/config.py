import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
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
    public_web_base_url: str = "http://localhost:3000"
    redis_url: str | None = None
    cache_ttl_stats_seconds: int = 300
    cache_ttl_trending_seconds: int = 300
    pilot_university_required: bool = True

    admin_email: str = "admin@example.com"
    admin_password: str = "admin123456"
    admin_full_name: str = "Platform Admin"

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

    @field_validator("s3_bucket", "s3_region", "s3_access_key_id", "s3_secret_access_key", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
