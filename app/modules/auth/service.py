from datetime import UTC, datetime, timedelta
from html import escape
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, ConflictError, ResourceNotFound
from app.core.security import (
    claims_expiration_to_datetime,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.security_controls import AccessTokenRevocationStore
from app.modules.audit.service import AuditService
from app.modules.auth.email_outbox import EmailOutboxService
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken, RefreshTokenSession
from app.modules.auth.schemas import (
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
from app.modules.catalog.repositories import UniversityRepository
from app.modules.catalog.models import University
from app.modules.catalog_proposals.enums import ProposalEntityType, ProposalStatus
from app.modules.catalog_proposals.models import CatalogProposalLog, UniversityProposal
from app.modules.telegram.enums import TelegramEventType
from app.modules.telegram.event_service import TelegramEventService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.utils.hashing import sha256_text
from app.utils.slug import slugify


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.universities = UniversityRepository(session)
        self.audit = AuditService(session)
        self.email_outbox = EmailOutboxService(session, self.settings)

    async def register(self, payload: RegisterRequest) -> User:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("User with this email already exists")
        university_id = payload.university_id
        pending_university_name: str | None = None
        if university_id:
            if not await self.universities.get(university_id):
                raise ResourceNotFound("University not found")
            university_status = "selected"
        else:
            pending_university_name = payload.proposed_university_name or ""
            await self._ensure_university_proposal_available(pending_university_name)
            university_status = "pending"

        user = User(
            full_name=payload.full_name,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            university_id=university_id,
            pending_university_name=pending_university_name,
            university_status=university_status,
        )
        await self.users.create(user)
        if pending_university_name:
            await self._create_registration_university_proposal(user, pending_university_name)
        await self.audit.log("user_registered", "user", user, user.id)
        verification_token = await self._create_email_verification_token(user)
        await self._queue_verification_email(user, verification_token)
        await TelegramEventService(self.session).enqueue_user_registered_events(user)
        await self.session.commit()
        return user

    async def _ensure_university_proposal_available(self, proposed_name: str) -> None:
        proposed_slug = slugify(proposed_name)
        existing_university = await self.session.execute(
            select(University).where(
                or_(
                    University.name.ilike(proposed_name),
                    University.slug == proposed_slug,
                )
            )
        )
        if existing_university.scalar_one_or_none():
            raise ConflictError("University already exists")
        pending_proposal = await self.session.execute(
            select(UniversityProposal).where(
                UniversityProposal.status == ProposalStatus.PENDING,
                or_(
                    UniversityProposal.proposed_name.ilike(proposed_name),
                    UniversityProposal.proposed_slug == proposed_slug,
                ),
            )
        )
        if pending_proposal.scalar_one_or_none():
            raise ConflictError("University proposal already exists")

    async def _create_registration_university_proposal(
        self,
        user: User,
        proposed_name: str,
    ) -> UniversityProposal:
        proposal = UniversityProposal(
            proposed_name=proposed_name,
            proposed_slug=slugify(proposed_name),
            proposed_description="Submitted during registration",
            created_by=user.id,
        )
        self.session.add(proposal)
        await self.session.flush()
        self.session.add(
            CatalogProposalLog(
                entity_type=ProposalEntityType.UNIVERSITY,
                entity_id=proposal.id,
                action="submitted_during_registration",
                actor_id=user.id,
            )
        )
        await TelegramEventService(self.session).enqueue_proposal_created_events(proposal, "university")
        return proposal

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")
        if not user.is_active:
            raise AuthenticationError("Hisobingiz bloklangan yoki nofaol. Iltimos, administrator bilan bog'laning.")
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
        if not user.is_active:
            raise AuthenticationError("Hisobingiz bloklangan yoki nofaol. Iltimos, administrator bilan bog'laning.")
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

    async def logout(
        self,
        payload: LogoutRequest | None,
        access_token: str | None = None,
    ) -> dict[str, str]:
        if access_token:
            await AccessTokenRevocationStore().revoke_token(access_token)
        if not payload or not payload.refresh_token:
            return {"message": "Tizimdan chiqildi"}
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        token_session = await self._get_refresh_session(claims["jti"], payload.refresh_token)
        token_session.revoked_at = datetime.now(UTC)
        await self.session.commit()
        return {"message": "Tizimdan chiqildi"}

    async def forgot_password(self, payload: ForgotPasswordRequest) -> dict[str, str]:
        user = await self.users.get_by_email(payload.email)
        if not user:
            return {
                "message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."
            }
        await self._consume_password_reset_tokens(user.id)
        token = uuid4().hex + uuid4().hex
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=sha256_text(token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session.add(reset_token)
        await self._queue_password_reset_email(user, token)
        await self.audit.log("password_reset_requested", "user", user, user.id)
        await TelegramEventService(self.session).enqueue_user_security_events(
            event_type=TelegramEventType.PASSWORD_RESET_REQUESTED,
            user=user,
            entity_id=reset_token.id,
        )
        await self.session.commit()
        return {"message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."}

    async def reset_password(self, payload: ResetPasswordRequest) -> dict[str, str]:
        result = await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == sha256_text(payload.token))
        )
        reset_token = result.scalar_one_or_none()
        if not reset_token or reset_token.consumed or reset_token.expires_at < datetime.now(UTC):
            raise AuthenticationError("Parolni tiklash tokeni noto'g'ri yoki muddati tugagan")
        user = await self.users.get_by_id(reset_token.user_id)
        if not user:
            raise ResourceNotFound("User not found")
        user.hashed_password = hash_password(payload.new_password)
        reset_token.consumed = True
        await self._revoke_all_refresh_tokens(user.id)
        await AccessTokenRevocationStore().revoke_all_for_user(user.id)
        await self.audit.log("password_reset_completed", "user", user, user.id)
        await TelegramEventService(self.session).enqueue_user_security_events(
            event_type=TelegramEventType.PASSWORD_CHANGED,
            user=user,
            entity_id=reset_token.id,
        )
        await self.session.commit()
        return {"message": "Parol tiklandi"}

    async def verify_email(self, payload: VerifyEmailRequest) -> dict[str, str]:
        result = await self.session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token == sha256_text(payload.token)
            )
        )
        verification_token = result.scalar_one_or_none()
        if (
            not verification_token
            or verification_token.consumed
            or verification_token.expires_at < datetime.now(UTC)
        ):
            raise AuthenticationError("Tasdiqlash tokeni noto'g'ri yoki muddati tugagan")
        user = await self.users.get_by_id(verification_token.user_id)
        if not user:
            raise ResourceNotFound("User not found")
        user.is_verified = True
        verification_token.consumed = True
        await self.audit.log("email_verified", "user", user, user.id)
        await TelegramEventService(self.session).enqueue_user_security_events(
            event_type=TelegramEventType.EMAIL_VERIFIED,
            user=user,
            entity_id=user.id,
        )
        await self.session.commit()
        return {"message": "Email tasdiqlandi"}

    async def resend_verification(self, payload: ResendVerificationRequest) -> dict[str, str]:
        user = await self.users.get_by_email(payload.email)
        if not user or user.is_verified:
            return {"message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."}
        verification_token = await self._create_email_verification_token(user)
        await self._queue_verification_email(user, verification_token)
        await self.audit.log("email_verification_requested", "user", user, user.id)
        await TelegramEventService(self.session).enqueue_user_security_events(
            event_type=TelegramEventType.EMAIL_VERIFICATION_RESENT,
            user=user,
            entity_id=user.id,
        )
        await self.session.commit()
        return {"message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."}

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
        return {"message": "Sessiya bekor qilindi"}

    async def logout_all(self, user: User) -> dict[str, str]:
        await self._revoke_all_refresh_tokens(user.id)
        await self.session.commit()
        return {"message": "Barcha sessiyalar bekor qilindi"}

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
        result = await self.session.execute(
            select(RefreshTokenSession)
            .where(RefreshTokenSession.jti == jti)
            .with_for_update()
        )
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

    async def _create_email_verification_token(self, user: User) -> str:
        await self._consume_email_verification_tokens(user.id)
        token = uuid4().hex + uuid4().hex
        self.session.add(
            EmailVerificationToken(
                user_id=user.id,
                token=sha256_text(token),
                expires_at=datetime.now(UTC)
                + timedelta(hours=self.settings.email_verification_token_expire_hours),
            )
        )
        return token

    async def _consume_email_verification_tokens(self, user_id: str) -> None:
        await self.session.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.consumed.is_(False),
            )
            .values(consumed=True)
        )

    async def _consume_password_reset_tokens(self, user_id: str) -> None:
        await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.consumed.is_(False),
            )
            .values(consumed=True)
        )

    async def _queue_verification_email(self, user: User, token: str) -> None:
        verification_url = self._build_public_url(self.settings.email_verification_url_path, token)
        await self.email_outbox.enqueue(
            recipient_email=user.email,
            subject="Verify your Student Knowledge Hub email",
            text_body=(
                f"Hello {user.full_name},\n\n"
                "Verify your email address using this link:\n"
                f"{verification_url}\n\n"
                "If you did not create this account, you can ignore this email."
            ),
            html_body=(
                f"<p>Hello {escape(user.full_name)},</p>"
                "<p>Verify your email address using this link:</p>"
                f'<p><a href="{escape(verification_url, quote=True)}">Verify email</a></p>'
                "<p>If you did not create this account, you can ignore this email.</p>"
            ),
        )

    async def _queue_password_reset_email(self, user: User, token: str) -> None:
        reset_url = self._build_public_url(self.settings.password_reset_url_path, token)
        await self.email_outbox.enqueue(
            recipient_email=user.email,
            subject="Reset your Student Knowledge Hub password",
            text_body=(
                f"Hello {user.full_name},\n\n"
                "Reset your password using this link:\n"
                f"{reset_url}\n\n"
                "If you did not request a password reset, you can ignore this email."
            ),
            html_body=(
                f"<p>Hello {escape(user.full_name)},</p>"
                "<p>Reset your password using this link:</p>"
                f'<p><a href="{escape(reset_url, quote=True)}">Reset password</a></p>'
                "<p>If you did not request a password reset, you can ignore this email.</p>"
            ),
        )

    def _build_public_url(self, path: str, token: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.settings.public_web_base_url.rstrip('/')}{normalized_path}?token={token}"
