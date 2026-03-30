from datetime import datetime

from pydantic import BaseModel, Field

from app.enums.material_status import MaterialStatus
from app.enums.material_type import MaterialType
from app.enums.reject_reason import RejectReason
from app.schemas.common import ORMModel
from app.schemas.material_file import MaterialFileRead
from app.schemas.summary import FacultySummary, PublicUserSummary, SubjectSummary, TagSummary, UniversitySummary


class MaterialCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    material_type: MaterialType
    subject_id: str
    cover_file_id: str | None = None
    primary_file_id: str | None = None


class MaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    material_type: MaterialType | None = None
    subject_id: str | None = None
    cover_file_id: str | None = None
    primary_file_id: str | None = None


class MaterialListQuery(BaseModel):
    q: str | None = None
    subject_id: str | None = None
    faculty_id: str | None = None
    university_id: str | None = None
    material_type: MaterialType | None = None
    semester: int | None = Field(default=None, ge=1, le=12)
    status: MaterialStatus | None = None
    file_format: str | None = None
    course: int | None = Field(default=None, ge=1, le=12)
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


class MaterialRead(ORMModel):
    id: str
    slug: str
    title: str
    description: str | None
    material_type: MaterialType
    status: MaterialStatus
    subject_id: str
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
