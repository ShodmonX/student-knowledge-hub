from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.catalog_proposals.enums import ProposalStatus
from app.shared.schemas.summary import PublicUserSummary


class UniversityProposalCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None


class FacultyProposalCreate(BaseModel):
    university_id: str
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None


class SubjectProposalCreate(BaseModel):
    faculty_id: str
    name: str = Field(min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    semester: int | None = Field(default=None, ge=1, le=12)
    description: str | None = None


class ProposalRejectRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=128)
    note: str | None = None


class ProposalApproveRequest(BaseModel):
    canonical_name: str | None = Field(default=None, max_length=255)
    canonical_slug: str | None = Field(default=None, max_length=255)
    canonical_description: str | None = None
    canonical_code: str | None = Field(default=None, max_length=64)
    canonical_semester: int | None = Field(default=None, ge=1, le=12)
    note: str | None = None


class ProposalMapExistingRequest(BaseModel):
    target_id: str
    note: str | None = None


class CatalogProposalRead(BaseModel):
    id: str
    proposal_type: str
    status: ProposalStatus
    proposed_name: str
    proposed_description: str | None = None
    parent_id: str | None = None
    proposed_code: str | None = None
    proposed_semester: int | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None
    creator: PublicUserSummary | None = None


class HomeUniversityUpdateRequest(BaseModel):
    university_id: str


class HomeUniversityUpdateResponse(BaseModel):
    message: str
    home_university_id: str
