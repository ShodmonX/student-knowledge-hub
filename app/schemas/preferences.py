from pydantic import BaseModel

from app.schemas.common import ORMModel


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
