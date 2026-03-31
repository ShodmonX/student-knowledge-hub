from datetime import datetime

from pydantic import BaseModel


class UniversitySummary(BaseModel):
    id: str
    name: str
    slug: str


class FacultySummary(BaseModel):
    id: str
    name: str
    slug: str
    university_id: str


class SubjectSummary(BaseModel):
    id: str
    name: str
    slug: str
    semester: int
    faculty_id: str


class PublicUserSummary(BaseModel):
    id: str
    full_name: str
    avatar_url: str | None = None
    university: UniversitySummary | None = None


class TagSummary(BaseModel):
    id: str
    name: str
    slug: str


class MaterialSummary(BaseModel):
    id: str
    title: str
    material_type: str
    download_count: int
    created_at: datetime
