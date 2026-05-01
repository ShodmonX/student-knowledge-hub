from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security_controls import AccessTokenRevocationStore, AuthRateLimiter
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, oauth2_scheme, optional_oauth2_scheme
from app.modules.auth.schemas import (
    AuthSessionRead,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User
from app.modules.users.schemas import UserRead
from app.shared.schemas.common import MessageResponse

router = APIRouter()
LOGOUT_PAYLOAD_BODY = Body(default=None)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    await AuthRateLimiter().check_register_rate(request, payload.email)
    user = await AuthService(session).register(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    limiter = AuthRateLimiter()
    await limiter.check_login_rate(request, payload.email)
    await limiter.check_login_lockout(request, payload.email)
    try:
        response = await AuthService(session).login(payload)
    except AuthenticationError:
        await limiter.record_login_failure(request, payload.email)
        raise
    await limiter.record_login_success(request, payload.email)
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    await AuthRateLimiter().check_refresh_rate(request, payload.refresh_token)
    return await AuthService(session).refresh(payload)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AuthRateLimiter().check_password_reset_request_rate(request, payload.email)
    return MessageResponse(**(await AuthService(session).forgot_password(payload)))


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AuthRateLimiter().check_password_reset_confirm_rate(request, payload.token)
    return MessageResponse(**(await AuthService(session).reset_password(payload)))


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AuthRateLimiter().check_sensitive_rate(request, payload.token, "auth.email.verify")
    return MessageResponse(**(await AuthService(session).verify_email(payload)))


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AuthRateLimiter().check_sensitive_rate(request, payload.email, "auth.email.resend")
    return MessageResponse(**(await AuthService(session).resend_verification(payload)))


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    access_token: Annotated[str | None, Depends(optional_oauth2_scheme)],
    payload: LogoutRequest | None = LOGOUT_PAYLOAD_BODY,
) -> MessageResponse:
    identity = payload.refresh_token if payload and payload.refresh_token else "anonymous"
    await AuthRateLimiter().check_sensitive_rate(request, identity, "auth.logout")
    return MessageResponse(**(await AuthService(session).logout(payload, access_token)))


@router.get("/sessions", response_model=list[AuthSessionRead])
async def list_sessions(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AuthSessionRead]:
    await AuthRateLimiter().check_sensitive_rate(request, user.id, "auth.sessions.list")
    items = await AuthService(session).list_sessions(user)
    now = datetime.now(UTC)
    return [
        AuthSessionRead(
            id=item.id,
            jti=item.jti,
            created_at=item.created_at,
            expires_at=item.expires_at,
            used_at=item.used_at,
            revoked_at=item.revoked_at,
            replaced_by_jti=item.replaced_by_jti,
            is_active=item.revoked_at is None and item.used_at is None and item.expires_at > now,
        )
        for item in items
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    request: Request,
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    await AuthRateLimiter().check_sensitive_rate(request, user.id, "auth.sessions.revoke")
    return MessageResponse(**(await AuthService(session).revoke_session(user, session_id)))


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    access_token: Annotated[str, Depends(oauth2_scheme)],
) -> MessageResponse:
    await AuthRateLimiter().check_sensitive_rate(request, user.id, "auth.logout_all")
    response = await AuthService(session).logout_all(user)
    await AccessTokenRevocationStore().revoke_token(access_token)
    return MessageResponse(**response)


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(user)
