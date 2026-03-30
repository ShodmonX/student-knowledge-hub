from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


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
