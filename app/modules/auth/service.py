from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, ResourceNotFound
from app.core.security import (
    claims_expiration_to_datetime,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.users.models import User
from app.modules.auth.models import PasswordResetToken, RefreshTokenSession
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.modules.catalog.repositories import UniversityRepository
from app.modules.users.repository import UserRepository
from app.modules.audit.service import AuditService
from app.utils.hashing import sha256_text


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.universities = UniversityRepository(session)
        self.audit = AuditService(session)

    async def register(self, payload: RegisterRequest) -> User:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("User with this email already exists")
        if not await self.universities.get(payload.university_id):
            raise ResourceNotFound("University not found")

        user = User(
            full_name=payload.full_name,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            university_id=payload.university_id,
        )
        await self.users.create(user)
        await self.audit.log("user_registered", "user", user, user.id)
        await self.session.commit()
        return user

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")
        tokens = await self._issue_token_pair(user)
        await self.session.commit()
        return TokenResponse(**tokens, role=user.role)

    async def refresh(self, payload: RefreshRequest) -> TokenResponse:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        user = await self.users.get_by_id(claims["sub"])
        if not user:
            raise AuthenticationError("User not found")
        token_session = await self._get_refresh_session(claims["jti"], payload.refresh_token)
        if token_session.user_id != user.id:
            await self._revoke_all_refresh_tokens(user.id)
            await self.session.commit()
            raise AuthenticationError("Invalid refresh token")
        if (
            token_session.revoked_at is not None
            or token_session.used_at is not None
            or token_session.expires_at <= datetime.now(UTC)
        ):
            await self._revoke_all_refresh_tokens(user.id)
            await self.session.commit()
            raise AuthenticationError("Refresh token has already been used or revoked")

        token_session.used_at = datetime.now(UTC)
        tokens = await self._issue_token_pair(user)
        new_claims = decode_token(tokens["refresh_token"])
        token_session.replaced_by_jti = new_claims["jti"]
        token_session.revoked_at = token_session.used_at
        await self.session.commit()
        return TokenResponse(**tokens, role=user.role)

    async def logout(self, payload: LogoutRequest | None) -> dict[str, str]:
        if not payload or not payload.refresh_token:
            return {"message": "Logged out"}
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        token_session = await self._get_refresh_session(claims["jti"], payload.refresh_token)
        token_session.revoked_at = datetime.now(UTC)
        await self.session.commit()
        return {"message": "Logged out"}

    async def forgot_password(self, payload: ForgotPasswordRequest) -> dict[str, str]:
        user = await self.users.get_by_email(payload.email)
        if not user:
            return {"message": "If the account exists, reset instructions have been generated."}
        token = uuid4().hex + uuid4().hex
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session.add(reset_token)
        await self.audit.log("password_reset_requested", "user", user, user.id)
        await self.session.commit()
        return {"message": "If the account exists, reset instructions have been generated."}

    async def reset_password(self, payload: ResetPasswordRequest) -> dict[str, str]:
        result = await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
        )
        reset_token = result.scalar_one_or_none()
        if not reset_token or reset_token.consumed or reset_token.expires_at < datetime.now(UTC):
            raise AuthenticationError("Invalid or expired reset token")
        user = await self.users.get_by_id(reset_token.user_id)
        if not user:
            raise ResourceNotFound("User not found")
        user.hashed_password = hash_password(payload.new_password)
        reset_token.consumed = True
        await self._revoke_all_refresh_tokens(user.id)
        await self.audit.log("password_reset_completed", "user", user, user.id)
        await self.session.commit()
        return {"message": "Password has been reset"}

    async def revoke_user_sessions(self, user_id: str) -> None:
        await self._revoke_all_refresh_tokens(user_id)

    async def list_sessions(self, user: User) -> list[RefreshTokenSession]:
        result = await self.session.execute(
            select(RefreshTokenSession)
            .where(RefreshTokenSession.user_id == user.id)
            .order_by(RefreshTokenSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_session(self, user: User, session_id: str) -> dict[str, str]:
        result = await self.session.execute(
            select(RefreshTokenSession).where(
                RefreshTokenSession.id == session_id,
                RefreshTokenSession.user_id == user.id,
            )
        )
        token_session = result.scalar_one_or_none()
        if not token_session:
            raise ResourceNotFound("Session not found")
        token_session.revoked_at = datetime.now(UTC)
        await self.session.commit()
        return {"message": "Session revoked"}

    async def logout_all(self, user: User) -> dict[str, str]:
        await self._revoke_all_refresh_tokens(user.id)
        await self.session.commit()
        return {"message": "All sessions revoked"}

    async def _issue_token_pair(self, user: User) -> dict[str, str]:
        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id, user.role.value)
        claims = decode_token(refresh_token)
        self.session.add(
            RefreshTokenSession(
                user_id=user.id,
                jti=claims["jti"],
                token_hash=sha256_text(refresh_token),
                expires_at=claims_expiration_to_datetime(claims),
            )
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def _get_refresh_session(self, jti: str, refresh_token: str) -> RefreshTokenSession:
        result = await self.session.execute(select(RefreshTokenSession).where(RefreshTokenSession.jti == jti))
        token_session = result.scalar_one_or_none()
        if not token_session or token_session.token_hash != sha256_text(refresh_token):
            claims = decode_token(refresh_token)
            await self._revoke_all_refresh_tokens(claims["sub"])
            await self.session.commit()
            raise AuthenticationError("Refresh token is invalid")
        return token_session

    async def _revoke_all_refresh_tokens(self, user_id: str) -> None:
        await self.session.execute(
            update(RefreshTokenSession)
            .where(
                RefreshTokenSession.user_id == user_id,
                RefreshTokenSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
