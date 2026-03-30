from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.summary import PublicUserSummary


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
