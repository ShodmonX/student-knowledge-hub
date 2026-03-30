from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TagCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str | None = Field(default=None, max_length=100)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    slug: str | None = Field(default=None, max_length=100)


class TagRead(ORMModel):
    id: str
    name: str
    slug: str
