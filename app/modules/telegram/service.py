from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import ResourceNotFound
from app.modules.audit.service import AuditService
from app.modules.catalog_proposals.models import FacultyProposal, SubjectProposal, UniversityProposal
from app.modules.catalog_proposals.schemas import ProposalApproveRequest, ProposalRejectRequest
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.materials.models import Material
from app.modules.moderation.schemas import RejectRequest
from app.modules.moderation.service import ModerationService
from app.modules.telegram.models import TelegramLink, TelegramLinkSession
from app.modules.telegram.schemas import (
    TelegramIdentityLookupResponse,
    TelegramInternalLinkResponse,
    TelegramLinkSessionRead,
    TelegramLinkStatusRead,
    TelegramMaterialModerationResponse,
    TelegramMaterialSummary,
    TelegramPlatformIdentity,
    TelegramProposalDetailResponse,
    TelegramProposalListItem,
    TelegramProposalListResponse,
    TelegramProposalMessagePayload,
    TelegramProposalModerationResponse,
    TelegramProposalSummary,
    TelegramUserRegistrationMessagePayload,
    TelegramUserPayload,
)
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.utils.hashing import sha256_text


class TelegramService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.audit = AuditService(session)
        self.catalog_proposals = CatalogProposalService(session)
        self.moderation = ModerationService(session)

    async def create_link_session(self, user: User) -> TelegramLinkSessionRead:
        await self.session.execute(
            update(TelegramLinkSession)
            .where(
                TelegramLinkSession.user_id == user.id,
                TelegramLinkSession.is_active.is_(True),
            )
            .values(is_active=False, revoked_at=datetime.now(UTC))
        )

        token = secrets.token_urlsafe(24)
        manual_code = f"TG-{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.telegram_link_session_ttl_seconds)
        db_session = TelegramLinkSession(
            user_id=user.id,
            token_hash=sha256_text(token),
            code_hash=sha256_text(manual_code),
            expires_at=expires_at,
        )
        self.session.add(db_session)
        await self.audit.log("telegram_link_session_created", "telegram_link_session", user, db_session.id)
        await self.session.commit()
        await self.session.refresh(db_session)
        return TelegramLinkSessionRead(
            session_id=db_session.id,
            deep_link_url=self.build_deep_link_url(token),
            manual_code=manual_code,
            expires_at=expires_at,
            expires_in_seconds=self.settings.telegram_link_session_ttl_seconds,
        )

    async def get_link_status(self, user: User) -> TelegramLinkStatusRead:
        link = await self._get_active_link_by_user_id(user.id)
        if not link:
            return TelegramLinkStatusRead(is_linked=False)
        return TelegramLinkStatusRead(
            is_linked=True,
            telegram_username=link.telegram_username,
            telegram_first_name=link.telegram_first_name,
            linked_at=link.linked_at,
        )

    async def unlink(self, user: User) -> dict[str, str]:
        link = await self._get_active_link_by_user_id(user.id)
        if not link:
            raise ResourceNotFound("Telegram link not found")
        link.is_active = False
        link.unlinked_at = datetime.now(UTC)
        await self.audit.log("telegram_unlinked", "telegram_link", user, link.id)
        await self.session.commit()
        return {"status": "unlinked"}

    async def unlink_by_telegram_user_id(self, telegram_user_id: int) -> TelegramInternalLinkResponse:
        link = await self._get_active_link_by_telegram_user_id(telegram_user_id)
        if not link:
            return TelegramInternalLinkResponse(status="not_linked")

        user = await self._get_user(link.user_id)
        link.is_active = False
        link.unlinked_at = datetime.now(UTC)
        await self.audit.log(
            "telegram_unlinked_by_internal_service",
            "telegram_link",
            user,
            link.id,
            str(telegram_user_id),
        )
        await self.session.commit()
        return TelegramInternalLinkResponse(
            status="unlinked",
            platform_user=self._build_platform_identity(user),
        )

    async def consume_token(self, token: str, telegram_user: TelegramUserPayload) -> TelegramInternalLinkResponse:
        db_session = await self._get_session_by_token(token)
        if not db_session:
            return TelegramInternalLinkResponse(status="token_invalid")
        return await self._consume_link_session(db_session, telegram_user, invalid_status="token_invalid", expired_status="token_expired")

    async def verify_code(self, code: str, telegram_user: TelegramUserPayload) -> TelegramInternalLinkResponse:
        db_session = await self._get_session_by_code(code)
        if not db_session:
            return TelegramInternalLinkResponse(status="invalid_code")
        return await self._consume_link_session(db_session, telegram_user, invalid_status="invalid_code", expired_status="expired_code")

    async def get_identity_by_telegram_user_id(self, telegram_user_id: int) -> TelegramIdentityLookupResponse:
        link = await self._get_active_link_by_telegram_user_id(telegram_user_id)
        if not link:
            return TelegramIdentityLookupResponse(is_linked=False)
        user = await self._get_user(link.user_id)
        return TelegramIdentityLookupResponse(
            is_linked=True,
            platform_user=TelegramPlatformIdentity(
                id=user.id,
                display_name=user.full_name,
                role=user.role.value,
                is_active=user.is_active,
            ),
        )

    async def get_proposal_detail(self, proposal_id: str) -> TelegramProposalDetailResponse:
        proposal, proposal_type = await self._get_any_proposal(proposal_id)
        creator = await self._get_user(proposal.created_by)
        return TelegramProposalDetailResponse(
            id=proposal.id,
            status=proposal.status.value,
            proposal_type=proposal_type,
            title=proposal.proposed_name,
            description=getattr(proposal, "proposed_description", None),
            submitted_by={
                "id": creator.id,
                "display_name": creator.full_name,
            },
            scope=self._build_scope(proposal),
            created_at=proposal.created_at,
        )

    async def approve_proposal(self, proposal_id: str, telegram_user_id: int) -> TelegramProposalModerationResponse:
        actor = await self._resolve_actor_from_telegram(telegram_user_id)
        if isinstance(actor, str):
            return TelegramProposalModerationResponse(status=actor)
        proposal, proposal_type = await self._get_any_proposal(proposal_id, allow_missing=True)
        if proposal is None:
            return TelegramProposalModerationResponse(status="not_found")
        try:
            moderated = await self._approve_by_type(proposal_type, proposal_id, actor)
        except Exception as exc:
            return TelegramProposalModerationResponse(status=self._map_proposal_exception(exc))
        return TelegramProposalModerationResponse(
            status="approved",
            proposal=self._build_proposal_summary(moderated, proposal_type),
            moderated_by={"user_id": actor.id, "display_name": actor.full_name},
            processed_at=moderated.reviewed_at,
        )

    async def reject_proposal(self, proposal_id: str, telegram_user_id: int, reason: str) -> TelegramProposalModerationResponse:
        actor = await self._resolve_actor_from_telegram(telegram_user_id)
        if isinstance(actor, str):
            return TelegramProposalModerationResponse(status=actor)
        proposal, proposal_type = await self._get_any_proposal(proposal_id, allow_missing=True)
        if proposal is None:
            return TelegramProposalModerationResponse(status="not_found")
        try:
            moderated = await self._reject_by_type(proposal_type, proposal_id, actor, reason)
        except Exception as exc:
            return TelegramProposalModerationResponse(status=self._map_proposal_exception(exc))
        return TelegramProposalModerationResponse(
            status="rejected",
            proposal=self._build_proposal_summary(moderated, proposal_type),
            moderated_by={"user_id": actor.id, "display_name": actor.full_name},
            reason=reason,
            processed_at=moderated.reviewed_at,
        )

    async def approve_material(self, material_id: str, telegram_user_id: int) -> TelegramMaterialModerationResponse:
        actor = await self._resolve_actor_from_telegram(telegram_user_id)
        if isinstance(actor, str):
            return TelegramMaterialModerationResponse(status=actor)
        try:
            moderated = await self.moderation.approve(material_id, actor)
        except Exception as exc:
            return TelegramMaterialModerationResponse(status=self._map_moderation_exception(exc))
        return TelegramMaterialModerationResponse(
            status="approved",
            material=self._build_material_summary(moderated),
            moderated_by={"user_id": actor.id, "display_name": actor.full_name},
            processed_at=moderated.reviewed_at,
        )

    async def reject_material(
        self,
        material_id: str,
        telegram_user_id: int,
        payload: RejectRequest,
    ) -> TelegramMaterialModerationResponse:
        actor = await self._resolve_actor_from_telegram(telegram_user_id)
        if isinstance(actor, str):
            return TelegramMaterialModerationResponse(status=actor)
        try:
            moderated = await self.moderation.reject(material_id, payload, actor)
        except Exception as exc:
            return TelegramMaterialModerationResponse(status=self._map_moderation_exception(exc))
        return TelegramMaterialModerationResponse(
            status="rejected",
            material=self._build_material_summary(moderated),
            moderated_by={"user_id": actor.id, "display_name": actor.full_name},
            reason=payload.reason.value,
            note=payload.note,
            processed_at=moderated.reviewed_at,
        )

    async def request_material_revision(
        self,
        material_id: str,
        telegram_user_id: int,
        payload: RejectRequest,
    ) -> TelegramMaterialModerationResponse:
        actor = await self._resolve_actor_from_telegram(telegram_user_id)
        if isinstance(actor, str):
            return TelegramMaterialModerationResponse(status=actor)
        try:
            moderated = await self.moderation.request_revision(material_id, payload, actor)
        except Exception as exc:
            return TelegramMaterialModerationResponse(status=self._map_moderation_exception(exc))
        return TelegramMaterialModerationResponse(
            status="revision_requested",
            material=self._build_material_summary(moderated),
            moderated_by={"user_id": actor.id, "display_name": actor.full_name},
            reason=payload.reason.value,
            note=payload.note,
            processed_at=moderated.reviewed_at,
        )

    async def list_pending_proposals(
        self,
        proposal_type: str | None,
        limit: int,
        offset: int,
    ) -> TelegramProposalListResponse:
        type_filter = self._pluralize_proposal_type(proposal_type) if proposal_type else None
        admin_actor = await self._get_any_admin_user()
        pending = await self.catalog_proposals.list_pending(admin_actor, type_filter)
        flattened: list[TelegramProposalListItem] = []
        for key, items in pending.items():
            singular_type = key[:-1]
            for proposal in items:
                creator = getattr(proposal, "creator", None)
                flattened.append(
                    TelegramProposalListItem(
                        id=proposal.id,
                        proposal_type=singular_type,
                        title=proposal.proposed_name,
                        created_at=proposal.created_at,
                        submitted_by_name=creator.full_name if creator else None,
                    )
                )
        flattened.sort(key=lambda item: item.created_at)
        sliced = flattened[offset : offset + limit]
        return TelegramProposalListResponse(items=sliced, total=len(flattened), limit=limit, offset=offset)

    async def get_proposal_message_payload(self, proposal_id: str) -> TelegramProposalMessagePayload:
        proposal, proposal_type = await self._get_any_proposal(proposal_id)
        creator = await self._get_user(proposal.created_by)
        return TelegramProposalMessagePayload(
            proposal_id=proposal.id,
            proposal_type=proposal_type,
            title=proposal.proposed_name,
            description=getattr(proposal, "proposed_description", None),
            submitted_by_name=creator.full_name,
            created_at=proposal.created_at,
            approve_callback_data=f"proposal:approve:{proposal.id}",
            reject_callback_data=f"proposal:reject:{proposal.id}",
        )

    async def get_user_registration_message_payload(self, user_id: str) -> TelegramUserRegistrationMessagePayload:
        user = await self._get_user(user_id)
        university = getattr(user, "university", None)
        return TelegramUserRegistrationMessagePayload(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            university_name=university.name if university else None,
            registered_at=user.created_at,
        )

    def build_deep_link_url(self, token: str) -> str:
        if not self.settings.telegram_bot_username:
            raise RuntimeError("TELEGRAM_BOT_USERNAME is not configured")
        return f"https://t.me/{self.settings.telegram_bot_username}?start=link_{token}"

    async def _consume_link_session(
        self,
        db_session: TelegramLinkSession,
        telegram_user: TelegramUserPayload,
        *,
        invalid_status: str,
        expired_status: str,
    ) -> TelegramInternalLinkResponse:
        now = datetime.now(UTC)
        if db_session.used_at is not None:
            return TelegramInternalLinkResponse(status="used_code" if invalid_status == "invalid_code" else "token_used")
        if not db_session.is_active or db_session.revoked_at is not None:
            return TelegramInternalLinkResponse(status=invalid_status)
        if db_session.expires_at <= now:
            db_session.is_active = False
            await self.session.commit()
            return TelegramInternalLinkResponse(status=expired_status)

        user = await self._get_user(db_session.user_id)
        existing_user_link = await self._get_link_by_user_id(user.id)
        if (
            existing_user_link
            and existing_user_link.is_active
            and existing_user_link.telegram_user_id == telegram_user.telegram_user_id
        ):
            db_session.used_at = now
            db_session.is_active = False
            await self.session.commit()
            return TelegramInternalLinkResponse(
                status="already_linked_to_this_account",
                platform_user=self._build_platform_identity(user),
            )

        existing_telegram_link = await self._get_link_by_telegram_user_id(telegram_user.telegram_user_id)
        if (
            existing_telegram_link
            and existing_telegram_link.is_active
            and existing_telegram_link.user_id != user.id
        ):
            return TelegramInternalLinkResponse(status="telegram_account_already_used")

        if (
            existing_user_link
            and existing_user_link.is_active
            and existing_user_link.telegram_user_id != telegram_user.telegram_user_id
        ):
            return TelegramInternalLinkResponse(status="platform_account_has_another_telegram")

        link = await self._resolve_link_record(existing_user_link, existing_telegram_link)
        if link is None:
            link = TelegramLink(
                user_id=user.id,
                telegram_user_id=telegram_user.telegram_user_id,
                linked_at=now,
            )
            self.session.add(link)

        link.user_id = user.id
        link.telegram_user_id = telegram_user.telegram_user_id
        link.telegram_username = telegram_user.username
        link.telegram_first_name = telegram_user.first_name
        link.telegram_last_name = telegram_user.last_name
        link.language_code = telegram_user.language_code
        link.linked_at = now
        link.unlinked_at = None
        link.is_active = True
        db_session.used_at = now
        db_session.is_active = False
        await self.audit.log("telegram_linked", "telegram_link", user, link.id, str(telegram_user.telegram_user_id))
        await self.session.commit()
        return TelegramInternalLinkResponse(
            status="linked_successfully",
            platform_user=self._build_platform_identity(user),
        )

    async def _get_session_by_token(self, token: str) -> TelegramLinkSession | None:
        result = await self.session.execute(
            select(TelegramLinkSession).where(TelegramLinkSession.token_hash == sha256_text(token))
        )
        return result.scalar_one_or_none()

    async def _get_session_by_code(self, code: str) -> TelegramLinkSession | None:
        result = await self.session.execute(
            select(TelegramLinkSession).where(TelegramLinkSession.code_hash == sha256_text(code))
        )
        return result.scalar_one_or_none()

    async def _get_active_link_by_user_id(self, user_id: str) -> TelegramLink | None:
        result = await self.session.execute(
            select(TelegramLink).where(TelegramLink.user_id == user_id, TelegramLink.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def _get_link_by_user_id(self, user_id: str) -> TelegramLink | None:
        result = await self.session.execute(select(TelegramLink).where(TelegramLink.user_id == user_id))
        return result.scalar_one_or_none()

    async def _get_active_link_by_telegram_user_id(self, telegram_user_id: int) -> TelegramLink | None:
        result = await self.session.execute(
            select(TelegramLink).where(
                TelegramLink.telegram_user_id == telegram_user_id,
                TelegramLink.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _get_link_by_telegram_user_id(self, telegram_user_id: int) -> TelegramLink | None:
        result = await self.session.execute(
            select(TelegramLink).where(TelegramLink.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def _resolve_link_record(
        self,
        existing_user_link: TelegramLink | None,
        existing_telegram_link: TelegramLink | None,
    ) -> TelegramLink | None:
        if existing_user_link and existing_telegram_link:
            if existing_user_link.id == existing_telegram_link.id:
                return existing_user_link
            await self.session.delete(existing_telegram_link)
            await self.session.flush()
            return existing_user_link
        if existing_user_link:
            return existing_user_link
        if existing_telegram_link:
            return existing_telegram_link
        return None

    async def _get_user(self, user_id: str) -> User:
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.university))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFound("User not found")
        return user

    async def _resolve_actor_from_telegram(self, telegram_user_id: int) -> User | str:
        link = await self._get_active_link_by_telegram_user_id(telegram_user_id)
        if not link:
            return "not_linked"
        user = await self._get_user(link.user_id)
        if not user.is_active:
            return "forbidden"
        return user

    async def _get_any_proposal(self, proposal_id: str, allow_missing: bool = False):
        for model, proposal_type in (
            (UniversityProposal, "university"),
            (FacultyProposal, "faculty"),
            (SubjectProposal, "subject"),
        ):
            result = await self.session.execute(
                select(model)
                .where(model.id == proposal_id)
                .options(selectinload(model.creator))
            )
            proposal = result.scalar_one_or_none()
            if proposal:
                return proposal, proposal_type
        if allow_missing:
            return None, None
        raise ResourceNotFound("Proposal not found")

    async def _approve_by_type(self, proposal_type: str, proposal_id: str, actor: User):
        payload = ProposalApproveRequest()
        if proposal_type == "university":
            return await self.catalog_proposals.approve_university(proposal_id, actor, payload)
        if proposal_type == "faculty":
            return await self.catalog_proposals.approve_faculty(proposal_id, actor, payload)
        return await self.catalog_proposals.approve_subject(proposal_id, actor, payload)

    async def _reject_by_type(self, proposal_type: str, proposal_id: str, actor: User, reason: str):
        payload = ProposalRejectRequest(reason=reason)
        if proposal_type == "university":
            return await self.catalog_proposals.reject_university(proposal_id, actor, payload)
        if proposal_type == "faculty":
            return await self.catalog_proposals.reject_faculty(proposal_id, actor, payload)
        return await self.catalog_proposals.reject_subject(proposal_id, actor, payload)

    async def _get_any_admin_user(self) -> User:
        result = await self.session.execute(
            select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at.asc()).limit(1)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFound("Admin user not found")
        return user

    @staticmethod
    def _build_platform_identity(user: User) -> TelegramPlatformIdentity:
        return TelegramPlatformIdentity(
            id=user.id,
            display_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        )

    @staticmethod
    def _build_scope(proposal) -> dict[str, str | None]:
        if isinstance(proposal, UniversityProposal):
            return {"university_id": None}
        if isinstance(proposal, FacultyProposal):
            return {"university_id": proposal.university_id}
        return {"faculty_id": proposal.faculty_id}

    @staticmethod
    def _build_proposal_summary(proposal, proposal_type: str) -> TelegramProposalSummary:
        return TelegramProposalSummary(
            id=proposal.id,
            proposal_type=proposal_type,
            title=proposal.proposed_name,
            status=proposal.status.value,
        )

    @staticmethod
    def _build_material_summary(material: Material) -> TelegramMaterialSummary:
        return TelegramMaterialSummary(
            id=material.id,
            title=material.title,
            status=material.status.value,
        )

    @staticmethod
    def _map_proposal_exception(exc: Exception) -> str:
        name = exc.__class__.__name__
        if name == "PermissionDenied":
            return "forbidden"
        if name == "ResourceNotFound":
            return "not_found"
        if name == "ConflictError":
            return "already_processed"
        return "invalid_state"

    @staticmethod
    def _map_moderation_exception(exc: Exception) -> str:
        name = exc.__class__.__name__
        if name == "PermissionDenied":
            return "forbidden"
        if name == "ResourceNotFound":
            return "not_found"
        if name == "ConflictError":
            return "already_processed"
        return "invalid_state"

    @staticmethod
    def _pluralize_proposal_type(proposal_type: str) -> str:
        mapping = {
            "university": "universities",
            "faculty": "faculties",
            "subject": "subjects",
        }
        return mapping.get(proposal_type, proposal_type)
