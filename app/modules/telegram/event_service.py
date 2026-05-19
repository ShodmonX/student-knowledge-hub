from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.admin.scope_models import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.modules.catalog.models import Faculty, Subject
from app.modules.catalog_proposals.models import FacultyProposal, SubjectProposal, UniversityProposal
from app.modules.materials.models import Material
from app.modules.telegram.enums import TelegramEventStatus, TelegramEventType
from app.modules.telegram.models import TelegramEventOutbox, TelegramLink
from app.modules.telegram.schemas import TelegramEventRecipient, TelegramOutboxEventListResponse, TelegramOutboxEventRead
from app.modules.users.enums import UserRole
from app.modules.users.models import User


class TelegramEventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def create_event(
        self,
        *,
        event_type: TelegramEventType,
        entity_type: str | None,
        entity_id: str | None,
        recipient: User,
        payload: dict,
        delivery_channel: str = "telegram_bot",
    ) -> TelegramEventOutbox:
        existing = await self.session.execute(
            select(TelegramEventOutbox).where(
                TelegramEventOutbox.event_type == event_type,
                TelegramEventOutbox.entity_id == entity_id,
                TelegramEventOutbox.recipient_user_id == recipient.id,
                TelegramEventOutbox.delivery_channel == delivery_channel,
            )
        )
        event = existing.scalar_one_or_none()
        if event:
            return event

        event = TelegramEventOutbox(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            recipient_user_id=recipient.id,
            recipient_role=recipient.role.value,
            delivery_channel=delivery_channel,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_pending_events(self, limit: int = 100) -> list[TelegramEventOutbox]:
        result = await self.session.execute(
            select(TelegramEventOutbox)
            .where(
                TelegramEventOutbox.status.in_(
                    [TelegramEventStatus.PENDING, TelegramEventStatus.FAILED]
                ),
                TelegramEventOutbox.attempt_count < self.settings.telegram_event_max_attempts,
            )
            .order_by(TelegramEventOutbox.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_dispatched(self, event: TelegramEventOutbox) -> TelegramEventOutbox:
        event.status = TelegramEventStatus.DISPATCHED
        event.attempt_count += 1
        event.last_error = None
        event.dispatched_at = datetime.now(UTC)
        await self.session.flush()
        return event

    async def mark_failed(self, event: TelegramEventOutbox, error: str) -> TelegramEventOutbox:
        event.status = TelegramEventStatus.FAILED
        event.attempt_count += 1
        event.last_error = error
        await self.session.flush()
        return event

    async def list_pending_event_items(self, limit: int = 100) -> TelegramOutboxEventListResponse:
        events = await self.list_pending_events(limit)
        items: list[TelegramOutboxEventRead] = []
        for event in events:
            items.append(await self.build_event_read(event))
        return TelegramOutboxEventListResponse(items=items, total=len(items), limit=limit)

    async def build_event_read(self, event: TelegramEventOutbox) -> TelegramOutboxEventRead:
        link = (
            await self.session.execute(
                select(TelegramLink).where(
                    TelegramLink.user_id == event.recipient_user_id,
                    TelegramLink.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return TelegramOutboxEventRead(
            event_id=event.id,
            event_type=event.event_type.value,
            occurred_at=event.created_at,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            delivery_channel=event.delivery_channel,
            recipient=TelegramEventRecipient(
                platform_user_id=event.recipient_user_id,
                role=event.recipient_role,
                telegram_user_id=link.telegram_user_id if link else None,
                telegram_username=link.telegram_username if link else None,
            ),
            payload=event.payload,
        )

    async def enqueue_user_registered_events(self, user: User) -> list[TelegramEventOutbox]:
        recipients = await self._list_admin_recipients()
        events: list[TelegramEventOutbox] = []
        for recipient in recipients:
            event = await self.create_event(
                event_type=TelegramEventType.USER_REGISTERED,
                entity_type="user",
                entity_id=user.id,
                recipient=recipient,
                payload={
                    "user_id": user.id,
                    "email": user.email,
                },
            )
            events.append(event)
        return events

    async def enqueue_telegram_account_linked_events(self, user: User, link: TelegramLink) -> list[TelegramEventOutbox]:
        recipients = await self._list_admin_recipients()
        events: list[TelegramEventOutbox] = []
        payload = {
            "telegram_username": link.telegram_username,
            "telegram_name": f"{link.telegram_first_name or ''} {link.telegram_last_name or ''}".strip(),
            "email": user.email,
            "full_name": user.full_name,
            "user_id": user.id,
        }
        for recipient in recipients:
            event = await self.create_event(
                event_type=TelegramEventType.TELEGRAM_ACCOUNT_LINKED,
                entity_type="telegram_link",
                entity_id=link.id,
                recipient=recipient,
                payload=payload,
            )
            events.append(event)
        return events

    async def enqueue_telegram_account_unlinked_events(self, user: User, link: TelegramLink) -> list[TelegramEventOutbox]:
        recipients = await self._list_admin_recipients()
        events: list[TelegramEventOutbox] = []
        payload = {
            "telegram_username": link.telegram_username,
            "telegram_name": f"{link.telegram_first_name or ''} {link.telegram_last_name or ''}".strip(),
            "email": user.email,
            "full_name": user.full_name,
            "user_id": user.id,
        }
        for recipient in recipients:
            event = await self.create_event(
                event_type=TelegramEventType.TELEGRAM_ACCOUNT_UNLINKED,
                entity_type="telegram_link",
                entity_id=link.id,
                recipient=recipient,
                payload=payload,
            )
            events.append(event)
        return events

    async def enqueue_user_security_events(
        self,
        *,
        event_type: TelegramEventType,
        user: User,
        entity_id: str,
        payload: dict | None = None,
    ) -> list[TelegramEventOutbox]:
        recipients = await self._list_admin_recipients()
        events: list[TelegramEventOutbox] = []
        for recipient in recipients:
            event = await self.create_event(
                event_type=event_type,
                entity_type="user",
                entity_id=entity_id,
                recipient=recipient,
                payload={
                    "user_id": user.id,
                    "email": user.email,
                    **(payload or {}),
                },
            )
            events.append(event)
        return events

    async def enqueue_material_submitted_events(
        self,
        material: Material,
        *,
        event_id: str,
    ) -> list[TelegramEventOutbox]:
        recipients = await self._resolve_material_recipients(material)
        payload = self._build_material_payload(material)
        events: list[TelegramEventOutbox] = []
        for recipient in recipients:
            event = await self.create_event(
                event_type=TelegramEventType.MATERIAL_SUBMITTED_FOR_REVIEW,
                entity_type="material",
                entity_id=event_id,
                recipient=recipient,
                payload=payload,
            )
            events.append(event)
        return events

    async def enqueue_material_owner_event(
        self,
        *,
        event_type: TelegramEventType,
        material: Material,
        actor: User,
        reason: str | None = None,
        note: str | None = None,
    ) -> list[TelegramEventOutbox]:
        owner = await self.session.get(User, material.uploaded_by)
        if not owner or not owner.is_active:
            return []
        event = await self.create_event(
            event_type=event_type,
            entity_type="material",
            entity_id=material.id,
            recipient=owner,
            payload={
                **self._build_material_payload(material),
                "reviewed_by": {
                    "user_id": actor.id,
                    "display_name": actor.full_name,
                    "role": actor.role.value,
                },
                "reason": reason,
                "note": note,
            },
        )
        return [event]

    async def enqueue_proposal_created_events(
        self,
        proposal: UniversityProposal | FacultyProposal | SubjectProposal,
        proposal_type: str,
    ) -> list[TelegramEventOutbox]:
        recipients = await self._resolve_proposal_recipients(proposal)
        events: list[TelegramEventOutbox] = []
        for recipient in recipients:
            event = await self.create_event(
                event_type=TelegramEventType.PROPOSAL_CREATED,
                entity_type="proposal",
                entity_id=proposal.id,
                recipient=recipient,
                payload={
                    "proposal_id": proposal.id,
                    "proposal_type": proposal_type,
                },
            )
            events.append(event)
        return events

    async def enqueue_proposal_owner_event(
        self,
        *,
        event_type: TelegramEventType,
        proposal: UniversityProposal | FacultyProposal | SubjectProposal,
        proposal_type: str,
        actor: User,
        note: str | None = None,
    ) -> list[TelegramEventOutbox]:
        owner = await self.session.get(User, proposal.created_by)
        if not owner or not owner.is_active:
            return []
        event = await self.create_event(
            event_type=event_type,
            entity_type="proposal",
            entity_id=proposal.id,
            recipient=owner,
            payload={
                "proposal_id": proposal.id,
                "proposal_type": proposal_type,
                "proposed_name": proposal.proposed_name,
                "reviewed_by": {
                    "user_id": actor.id,
                    "display_name": actor.full_name,
                    "role": actor.role.value,
                },
                "note": note,
            },
        )
        return [event]

    async def _list_admin_recipients(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).order_by(User.created_at.asc())
        )
        return list(result.scalars().all())

    async def _resolve_proposal_recipients(
        self,
        proposal: UniversityProposal | FacultyProposal | SubjectProposal,
    ) -> list[User]:
        recipient_ids = {user.id for user in await self._list_admin_recipients()}
        if isinstance(proposal, UniversityProposal):
            return await self._load_users_by_ids(recipient_ids)

        if isinstance(proposal, FacultyProposal):
            university_id = proposal.university_id
            uni_scope_result = await self.session.execute(
                select(ModeratorUniversityScope.user_id).where(ModeratorUniversityScope.university_id == university_id)
            )
            fac_scope_result = await self.session.execute(
                select(ModeratorFacultyScope.user_id)
                .join(Faculty, Faculty.id == ModeratorFacultyScope.faculty_id)
                .where(Faculty.university_id == university_id)
            )
            recipient_ids.update(uni_scope_result.scalars().all())
            recipient_ids.update(fac_scope_result.scalars().all())
            return await self._load_users_by_ids(recipient_ids)

        faculty = await self.session.get(Faculty, proposal.faculty_id)
        if faculty:
            uni_scope_result = await self.session.execute(
                select(ModeratorUniversityScope.user_id).where(ModeratorUniversityScope.university_id == faculty.university_id)
            )
            fac_scope_result = await self.session.execute(
                select(ModeratorFacultyScope.user_id).where(ModeratorFacultyScope.faculty_id == proposal.faculty_id)
            )
            sub_scope_result = await self.session.execute(
                select(ModeratorSubjectScope.user_id)
                .join(Subject, Subject.id == ModeratorSubjectScope.subject_id)
                .where(Subject.faculty_id == proposal.faculty_id)
            )
            recipient_ids.update(uni_scope_result.scalars().all())
            recipient_ids.update(fac_scope_result.scalars().all())
            recipient_ids.update(sub_scope_result.scalars().all())
        return await self._load_users_by_ids(recipient_ids)

    async def _resolve_material_recipients(self, material: Material) -> list[User]:
        recipient_ids = {user.id for user in await self._list_admin_recipients()}
        subject = await self.session.get(Subject, material.subject_id)
        if not subject:
            return await self._load_users_by_ids(recipient_ids)
        faculty = await self.session.get(Faculty, subject.faculty_id)

        sub_scope_result = await self.session.execute(
            select(ModeratorSubjectScope.user_id).where(ModeratorSubjectScope.subject_id == subject.id)
        )
        fac_scope_result = await self.session.execute(
            select(ModeratorFacultyScope.user_id).where(ModeratorFacultyScope.faculty_id == subject.faculty_id)
        )
        recipient_ids.update(sub_scope_result.scalars().all())
        recipient_ids.update(fac_scope_result.scalars().all())

        if faculty:
            uni_scope_result = await self.session.execute(
                select(ModeratorUniversityScope.user_id).where(
                    ModeratorUniversityScope.university_id == faculty.university_id
                )
            )
            recipient_ids.update(uni_scope_result.scalars().all())
        return await self._load_users_by_ids(recipient_ids)

    def _build_material_payload(self, material: Material) -> dict:
        subject = getattr(material, "subject", None)
        faculty = getattr(subject, "faculty", None) if subject else None
        university = getattr(faculty, "university", None) if faculty else None
        return {
            "material_id": material.id,
            "title": material.title,
            "subject_id": material.subject_id,
            "owner_user_id": material.uploaded_by,
            "status": material.status.value,
            "frontend_url": f"{self.settings.public_web_base_url.rstrip('/')}/materials/{material.slug}",
            "university": (
                {"id": university.id, "name": university.name, "slug": university.slug}
                if university
                else None
            ),
            "faculty": (
                {
                    "id": faculty.id,
                    "name": faculty.name,
                    "slug": faculty.slug,
                    "university_id": faculty.university_id,
                }
                if faculty
                else None
            ),
            "subject": (
                {
                    "id": subject.id,
                    "name": subject.name,
                    "slug": subject.slug,
                    "semester": subject.semester,
                    "faculty_id": subject.faculty_id,
                }
                if subject
                else None
            ),
        }

    async def _load_users_by_ids(self, user_ids: set[str]) -> list[User]:
        if not user_ids:
            return []
        result = await self.session.execute(
            select(User)
            .where(User.id.in_(user_ids), User.is_active.is_(True))
            .order_by(User.created_at.asc())
        )
        return list(result.scalars().all())
