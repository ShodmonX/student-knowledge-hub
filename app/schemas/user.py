from pydantic import EmailStr
from pydantic import BaseModel, Field

from app.enums.user_role import UserRole
from app.schemas.common import ORMModel
from app.schemas.summary import UniversitySummary


class PublicUserRead(ORMModel):
    id: str
    full_name: str
    avatar_url: str | None
    university: UniversitySummary | None = None


class UserRead(ORMModel):
    id: str
    full_name: str
    email: EmailStr
    avatar_url: str | None
    role: UserRole
    university_id: str
    is_active: bool
    is_verified: bool


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)
