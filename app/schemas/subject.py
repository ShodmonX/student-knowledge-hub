from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SubjectCreate(BaseModel):
    faculty_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = None
    code: str | None = Field(default=None, max_length=64)
    semester: int = Field(ge=1, le=12)
    description: str | None = None


class SubjectUpdate(BaseModel):
    faculty_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = None
    code: str | None = Field(default=None, max_length=64)
    semester: int | None = Field(default=None, ge=1, le=12)
    description: str | None = None


class SubjectRead(ORMModel):
    id: str
    faculty_id: str
    name: str
    slug: str
    code: str | None
    semester: int
    description: str | None
