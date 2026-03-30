from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


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
