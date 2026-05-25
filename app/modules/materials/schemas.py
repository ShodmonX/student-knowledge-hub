from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.materials.enums import FileKind, MaterialStatus, MaterialType, RejectReason
from app.shared.schemas.common import ORMModel
from app.shared.schemas.summary import (
    FacultySummary,
    PublicUserSummary,
    SubjectSummary,
    TagSummary,
    UniversitySummary,
)


class MaterialFileOrderInput(BaseModel):
    file_order: int = Field(ge=0)


class MaterialFileReorderRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class MaterialFileSelectionUpdate(BaseModel):
    cover: bool | None = None
    primary: bool | None = None


class AcceptedFileFormatsResponse(BaseModel):
    accepted_extensions: list[str]
    image_extensions: list[str]
    document_extensions: list[str]
    max_file_size: int
    max_total_size: int
    max_file_count: int


class MaterialFileRead(ORMModel):
    id: str
    material_id: str
    storage_key: str | None = None
    preview_storage_key: str | None = None
    original_filename: str
    mime_type: str
    file_size: int
    file_ext: str
    file_kind: FileKind
    file_order: int
    checksum_hash: str | None = None
    is_previewable: bool
    preview_page_count: int | None = None


class MaterialCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    material_type: MaterialType
    subject_id: str
    semesters: list[int] = Field(default_factory=list)
    cover_file_id: str | None = None
    primary_file_id: str | None = None


class MaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    material_type: MaterialType | None = None
    subject_id: str | None = None
    semesters: list[int] | None = None
    cover_file_id: str | None = None
    primary_file_id: str | None = None


class MaterialListQuery(BaseModel):
    q: str | None = None
    subject_id: str | None = None
    faculty_id: str | None = None
    university_id: str | None = None
    material_type: MaterialType | None = None
    semester: int | None = Field(default=None, ge=1, le=14)
    status: MaterialStatus | None = None
    file_format: str | None = None
    course: int | None = Field(default=None, ge=1, le=14)
    is_public: bool | None = None
    only_approved: bool | None = None
    uploaded_by: str | None = None
    download_count_gte: int | None = Field(default=None, ge=0)
    sort: str = "created_at_desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class MaterialReportCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=128)
    details: str | None = None


class MaterialPreviewResponse(BaseModel):
    preview_url: str | None
    preview_type: str


class MaterialRead(ORMModel):
    id: str
    slug: str
    title: str
    description: str | None
    material_type: MaterialType
    status: MaterialStatus
    subject_id: str
    semesters: list[int]
    uploaded_by: str
    approved_by: str | None
    last_reviewed_by: str | None
    rejected_reason: RejectReason | None
    cover_file_id: str | None
    primary_file_id: str | None
    file_count: int
    total_size: int
    download_count: int
    submitted_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    files: list[MaterialFileRead] = []
    uploader: PublicUserSummary | None = None
    subject: SubjectSummary | None = None
    faculty: FacultySummary | None = None
    university: UniversitySummary | None = None
    tags: list[TagSummary] = []
    average_rating: float = 0.0
    rating_count: int = 0
    access_level: str = "public"
    can_download: bool = False
    can_preview: bool = False
    requires_auth_for_download: bool = True
    preview_page_limit: int | None = None


class MaterialStatsSummary(BaseModel):
    total_materials: int
    approved_materials: int
    pending_materials: int
    total_downloads: int
