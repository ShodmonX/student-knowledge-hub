from pydantic import BaseModel, EmailStr, Field

from app.modules.users.enums import UserRole
from app.shared.schemas.common import ORMModel
from app.shared.schemas.summary import UniversitySummary


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
    university_id: str | None
    pending_university_name: str | None = None
    university_status: str = "selected"
    is_active: bool
    is_verified: bool


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)


class UserPreferenceRead(ORMModel):
    language: str
    email_notifications: bool
    marketing_notifications: bool
    theme: str


class UserPreferenceUpdate(BaseModel):
    language: str | None = None
    email_notifications: bool | None = None
    marketing_notifications: bool | None = None
    theme: str | None = None
