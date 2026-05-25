from pydantic import BaseModel, Field

from app.shared.schemas.common import ORMModel


class UniversityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = None


class UniversityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = None


class UniversityRead(ORMModel):
    id: str
    name: str
    slug: str


class FacultyCreate(BaseModel):
    university_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = None


class FacultyUpdate(BaseModel):
    university_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = None


class FacultyRead(ORMModel):
    id: str
    university_id: str
    name: str
    slug: str


class SubjectCreate(BaseModel):
    faculty_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = None
    code: str | None = Field(default=None, max_length=64)
    description: str | None = None


class SubjectUpdate(BaseModel):
    faculty_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = None
    code: str | None = Field(default=None, max_length=64)
    description: str | None = None


class SubjectRead(ORMModel):
    id: str
    faculty_id: str
    name: str
    slug: str
    code: str | None
    description: str | None


class SubjectTreeRead(BaseModel):
    id: str
    faculty_id: str
    name: str
    slug: str
    code: str | None
    description: str | None


class FacultyTreeRead(BaseModel):
    id: str
    university_id: str
    name: str
    slug: str
    subjects: list[SubjectTreeRead]


class UniversityTreeRead(BaseModel):
    id: str
    name: str
    slug: str
    faculties: list[FacultyTreeRead]
