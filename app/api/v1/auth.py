from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthSessionRead,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    user = await AuthService(session).register(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    return await AuthService(session).login(payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    return await AuthService(session).refresh(payload)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    return MessageResponse(**(await AuthService(session).forgot_password(payload)))


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    return MessageResponse(**(await AuthService(session).reset_password(payload)))


@router.post("/logout", response_model=MessageResponse)
async def logout(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: LogoutRequest | None = Body(default=None),
) -> MessageResponse:
    return MessageResponse(**(await AuthService(session).logout(payload)))


@router.get("/sessions", response_model=list[AuthSessionRead])
async def list_sessions(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AuthSessionRead]:
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
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    return MessageResponse(**(await AuthService(session).revoke_session(user, session_id)))


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    return MessageResponse(**(await AuthService(session).logout_all(user)))


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(user)
