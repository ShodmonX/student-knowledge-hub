from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.schemas.summary import PublicUserSummary


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class CommentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class CommentRead(BaseModel):
    id: str
    material_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    user: PublicUserSummary


class RatingCreate(BaseModel):
    value: int = Field(ge=1, le=5)


class RatingSummary(BaseModel):
    average: float
    total: int
    my_rating: int | None = None
