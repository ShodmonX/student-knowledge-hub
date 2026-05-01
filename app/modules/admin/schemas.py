from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.materials.enums import ReportStatus
from app.shared.schemas.summary import MaterialSummary, PublicUserSummary


class ModeratorScopeCreate(BaseModel):
    university_id: str | None = None
    faculty_id: str | None = None
    subject_id: str | None = None


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)
    university_id: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class MaterialReportRead(BaseModel):
    id: str
    reason: str
    details: str | None
    status: ReportStatus
    resolution_note: str | None
    reviewed_at: datetime | None
    created_at: datetime
    reporter: PublicUserSummary
    material: MaterialSummary


class BackupRead(BaseModel):
    backup_id: str
    created_at: datetime
    database_name: str
    dump_format: str
    checksum_sha256: str
    size_bytes: int
    verified: bool
    trigger: str
    local_dump_path: str | None = None
    local_manifest_path: str | None = None
    offsite_enabled: bool
    offsite_bucket: str | None = None
    offsite_dump_key: str | None = None
    offsite_manifest_key: str | None = None
    available_local: bool
    available_offsite: bool


class BackupListResponse(BaseModel):
    items: list[BackupRead]
    total: int


class BackupRestoreResponse(BaseModel):
    restored_backup: BackupRead
    pre_restore_backup: BackupRead
    restored_at: datetime


class BackupRestoreRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=255)
