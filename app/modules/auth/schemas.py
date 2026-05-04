from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.users.enums import UserRole


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    university_id: str | None = None
    proposed_university_name: str | None = Field(default=None, min_length=2, max_length=255)

    @model_validator(mode="after")
    def validate_university_choice(self) -> "RegisterRequest":
        has_existing = bool(self.university_id)
        has_proposal = bool(self.proposed_university_name and self.proposed_university_name.strip())
        if has_existing == has_proposal:
            raise ValueError("Provide exactly one of university_id or proposed_university_name")
        if self.proposed_university_name:
            self.proposed_university_name = self.proposed_university_name.strip()
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AuthSessionRead(BaseModel):
    id: str
    jti: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    replaced_by_jti: str | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: UserRole
