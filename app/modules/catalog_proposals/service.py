from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, PermissionDenied, ResourceNotFound, ValidationAppError
from app.modules.catalog_proposals.enums import ProposalEntityType, ProposalStatus
from app.modules.admin.scope_models import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.users.models import User
from app.modules.catalog_proposals.models import (
    CatalogProposalLog,
    FacultyProposal,
    SubjectProposal,
    UniversityProposal,
)
from app.modules.catalog_proposals.schemas import (
    FacultyProposalCreate,
    HomeUniversityUpdateRequest,
    SubjectProposalCreate,
    UniversityProposalCreate,
)
from app.modules.telegram.event_service import TelegramEventService
from app.utils.slug import slugify

HOME_UNIVERSITY_COOLDOWN_DAYS = 45


class CatalogProposalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_university_proposal(self, payload: UniversityProposalCreate, user: User) -> UniversityProposal:
        proposed_name = payload.name.strip()
        if not proposed_name:
            raise ValidationAppError("University name is required")
        duplicate = await self.session.execute(
            select(University).where(or_(University.name.ilike(proposed_name), University.slug == slugify(proposed_name)))
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError("University already exists")
        proposal = UniversityProposal(
            proposed_name=proposed_name,
            proposed_slug=slugify(proposed_name),
            proposed_description=payload.description,
            created_by=user.id,
        )
        self.session.add(proposal)
        await self.session.flush()
        await self._log(ProposalEntityType.UNIVERSITY, proposal.id, "submitted", user.id)
        await TelegramEventService(self.session).enqueue_proposal_created_events(proposal, "university")
        await self.session.commit()
        return proposal

    async def create_faculty_proposal(self, payload: FacultyProposalCreate, user: User) -> FacultyProposal:
        university = await self.session.get(University, payload.university_id)
        if not university:
            raise ResourceNotFound("University not found")
        proposed_name = payload.name.strip()
        await self._ensure_faculty_name_available(payload.university_id, proposed_name)
        await self._ensure_pending_faculty_proposal_name_available(payload.university_id, proposed_name)
        duplicate = await self.session.execute(
            select(Faculty).where(
                Faculty.university_id == payload.university_id,
                or_(Faculty.name.ilike(proposed_name), Faculty.slug == slugify(proposed_name)),
            )
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError("Faculty already exists in this university")
        proposal = FacultyProposal(
            university_id=payload.university_id,
            proposed_name=proposed_name,
            proposed_slug=slugify(proposed_name),
            proposed_description=payload.description,
            created_by=user.id,
        )
        self.session.add(proposal)
        await self.session.flush()
        await self._log(ProposalEntityType.FACULTY, proposal.id, "submitted", user.id)
        await TelegramEventService(self.session).enqueue_proposal_created_events(proposal, "faculty")
        await self.session.commit()
        return proposal

    async def create_subject_proposal(self, payload: SubjectProposalCreate, user: User) -> SubjectProposal:
        faculty = await self.session.get(Faculty, payload.faculty_id)
        if not faculty:
            raise ResourceNotFound("Faculty not found")
        proposed_name = payload.name.strip()
        target_semester = payload.semester or 1
        await self._ensure_subject_name_available(payload.faculty_id, proposed_name, target_semester)
        await self._ensure_pending_subject_proposal_name_available(payload.faculty_id, proposed_name, target_semester)
        duplicate = await self.session.execute(
            select(Subject).where(
                Subject.faculty_id == payload.faculty_id,
                Subject.semester == target_semester,
                or_(Subject.name.ilike(proposed_name), Subject.slug == slugify(proposed_name)),
            )
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError("Subject already exists in this faculty")
        proposal = SubjectProposal(
            faculty_id=payload.faculty_id,
            proposed_name=proposed_name,
            proposed_slug=slugify(proposed_name),
            proposed_code=payload.code,
            proposed_semester=payload.semester,
            proposed_description=payload.description,
            created_by=user.id,
        )
        self.session.add(proposal)
        await self.session.flush()
        await self._log(ProposalEntityType.SUBJECT, proposal.id, "submitted", user.id)
        await TelegramEventService(self.session).enqueue_proposal_created_events(proposal, "subject")
        await self.session.commit()
        return proposal

    async def list_user_proposals(self, user: User, proposal_model):
        result = await self.session.execute(
            select(proposal_model)
            .options(selectinload(proposal_model.creator))
            .where(proposal_model.created_by == user.id)
            .order_by(proposal_model.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_home_university(self, user: User, payload: HomeUniversityUpdateRequest) -> dict:
        university = await self.session.get(University, payload.university_id)
        if not university:
            raise ResourceNotFound("University not found")
        if user.university_id == payload.university_id:
            raise ConflictError("Home university is already set to this value")
        now = datetime.now(UTC)
        if user.university_changed_at and now - user.university_changed_at < timedelta(days=HOME_UNIVERSITY_COOLDOWN_DAYS):
            next_allowed_at = user.university_changed_at + timedelta(days=HOME_UNIVERSITY_COOLDOWN_DAYS)
            raise ValidationAppError(
                "Home university can only be changed once every 45 days",
                {
                    "error_code": "university_change_cooldown",
                    "next_allowed_at": next_allowed_at.isoformat(),
                },
            )
        user.university_id = payload.university_id
        user.university_changed_at = now
        await self.session.commit()
        return {
            "message": "Asosiy universitet yangilandi",
            "home_university_id": user.university_id,
        }

    async def list_pending(self, actor: User, proposal_type: str | None = None) -> dict[str, list]:
        university_items = await self._list_pending_university_proposals(actor) if proposal_type in {None, "universities"} else []
        faculty_items = await self._list_pending_faculty_proposals(actor) if proposal_type in {None, "faculties"} else []
        subject_items = await self._list_pending_subject_proposals(actor) if proposal_type in {None, "subjects"} else []
        return {
            "universities": university_items,
            "faculties": faculty_items,
            "subjects": subject_items,
        }

    async def approve_university(self, proposal_id: str, actor: User, payload) -> UniversityProposal:
        self._require_admin(actor)
        proposal = await self._get_proposal(UniversityProposal, proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("Proposal is not pending")
        canonical_name = payload.canonical_name or proposal.proposed_name
        canonical_slug = payload.canonical_slug or proposal.proposed_slug or slugify(proposal.proposed_name)
        await self._ensure_university_name_available(canonical_name)
        await self._ensure_university_slug_available(canonical_slug)
        university = University(
            name=canonical_name,
            slug=canonical_slug,
        )
        self.session.add(university)
        await self.session.flush()
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = payload.note
        proposal.approved_university_id = university.id
        await self._log(ProposalEntityType.UNIVERSITY, proposal.id, "approved", actor.id, payload.note)
        await self.session.commit()
        return proposal

    async def reject_university(self, proposal_id: str, actor: User, payload) -> UniversityProposal:
        self._require_admin(actor)
        proposal = await self._get_proposal(UniversityProposal, proposal_id)
        return await self._reject_proposal(proposal, ProposalEntityType.UNIVERSITY, actor, payload.reason, payload.note)

    async def map_existing_university(self, proposal_id: str, actor: User, target_id: str, note: str | None) -> UniversityProposal:
        self._require_admin(actor)
        proposal = await self._get_proposal(UniversityProposal, proposal_id)
        if not await self.session.get(University, target_id):
            raise ResourceNotFound("University not found")
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = note
        proposal.approved_university_id = target_id
        await self._log(ProposalEntityType.UNIVERSITY, proposal.id, "mapped_to_existing", actor.id, note)
        await self.session.commit()
        return proposal

    async def approve_faculty(self, proposal_id: str, actor: User, payload) -> FacultyProposal:
        proposal = await self._get_proposal(FacultyProposal, proposal_id)
        await self._assert_faculty_proposal_scope(actor, proposal)
        canonical_name = payload.canonical_name or proposal.proposed_name
        canonical_slug = payload.canonical_slug or proposal.proposed_slug or slugify(proposal.proposed_name)
        await self._ensure_faculty_name_available(proposal.university_id, canonical_name)
        await self._ensure_faculty_slug_available(proposal.university_id, canonical_slug)
        faculty = Faculty(
            university_id=proposal.university_id,
            name=canonical_name,
            slug=canonical_slug,
        )
        self.session.add(faculty)
        await self.session.flush()
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = payload.note
        proposal.approved_faculty_id = faculty.id
        await self._log(ProposalEntityType.FACULTY, proposal.id, "approved", actor.id, payload.note)
        await self.session.commit()
        return proposal

    async def reject_faculty(self, proposal_id: str, actor: User, payload) -> FacultyProposal:
        proposal = await self._get_proposal(FacultyProposal, proposal_id)
        await self._assert_faculty_proposal_scope(actor, proposal)
        return await self._reject_proposal(proposal, ProposalEntityType.FACULTY, actor, payload.reason, payload.note)

    async def map_existing_faculty(self, proposal_id: str, actor: User, target_id: str, note: str | None) -> FacultyProposal:
        proposal = await self._get_proposal(FacultyProposal, proposal_id)
        await self._assert_faculty_proposal_scope(actor, proposal)
        faculty = await self.session.get(Faculty, target_id)
        if not faculty:
            raise ResourceNotFound("Faculty not found")
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = note
        proposal.approved_faculty_id = faculty.id
        await self._log(ProposalEntityType.FACULTY, proposal.id, "mapped_to_existing", actor.id, note)
        await self.session.commit()
        return proposal

    async def approve_subject(self, proposal_id: str, actor: User, payload) -> SubjectProposal:
        proposal = await self._get_proposal(SubjectProposal, proposal_id)
        await self._assert_subject_proposal_scope(actor, proposal)
        canonical_name = payload.canonical_name or proposal.proposed_name
        canonical_slug = payload.canonical_slug or proposal.proposed_slug or slugify(proposal.proposed_name)
        canonical_semester = payload.canonical_semester or proposal.proposed_semester or 1
        await self._ensure_subject_name_available(proposal.faculty_id, canonical_name, canonical_semester)
        await self._ensure_subject_slug_available(proposal.faculty_id, canonical_slug, canonical_semester)
        subject = Subject(
            faculty_id=proposal.faculty_id,
            name=canonical_name,
            slug=canonical_slug,
            code=payload.canonical_code or proposal.proposed_code,
            semester=canonical_semester,
            description=payload.canonical_description or proposal.proposed_description,
        )
        self.session.add(subject)
        await self.session.flush()
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = payload.note
        proposal.approved_subject_id = subject.id
        await self._log(ProposalEntityType.SUBJECT, proposal.id, "approved", actor.id, payload.note)
        await self.session.commit()
        return proposal

    async def reject_subject(self, proposal_id: str, actor: User, payload) -> SubjectProposal:
        proposal = await self._get_proposal(SubjectProposal, proposal_id)
        await self._assert_subject_proposal_scope(actor, proposal)
        return await self._reject_proposal(proposal, ProposalEntityType.SUBJECT, actor, payload.reason, payload.note)

    async def map_existing_subject(self, proposal_id: str, actor: User, target_id: str, note: str | None) -> SubjectProposal:
        proposal = await self._get_proposal(SubjectProposal, proposal_id)
        await self._assert_subject_proposal_scope(actor, proposal)
        subject = await self.session.get(Subject, target_id)
        if not subject:
            raise ResourceNotFound("Subject not found")
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = note
        proposal.approved_subject_id = subject.id
        await self._log(ProposalEntityType.SUBJECT, proposal.id, "mapped_to_existing", actor.id, note)
        await self.session.commit()
        return proposal

    async def _reject_proposal(self, proposal, entity_type: ProposalEntityType, actor: User, reason: str, note: str | None):
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("Proposal is not pending")
        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_by = actor.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = note or reason
        await self._log(entity_type, proposal.id, "rejected", actor.id, note or reason)
        await self.session.commit()
        return proposal

    async def _get_proposal(self, model, proposal_id: str):
        proposal = await self.session.get(model, proposal_id)
        if not proposal:
            raise ResourceNotFound("Proposal not found")
        return proposal

    async def _list_pending_university_proposals(self, actor: User):
        self._require_admin(actor)
        result = await self.session.execute(
            select(UniversityProposal)
            .options(selectinload(UniversityProposal.creator))
            .where(UniversityProposal.status == ProposalStatus.PENDING)
            .order_by(UniversityProposal.created_at.asc())
        )
        return list(result.scalars().all())

    async def _list_pending_faculty_proposals(self, actor: User):
        statement = (
            select(FacultyProposal)
            .options(selectinload(FacultyProposal.creator))
            .where(FacultyProposal.status == ProposalStatus.PENDING)
            .order_by(FacultyProposal.created_at.asc())
        )
        if actor.role.value == "admin":
            result = await self.session.execute(statement)
            return list(result.scalars().all())
        uni_ids, fac_ids, _ = await self._scope_ids(actor.id)
        if not uni_ids and not fac_ids:
            return []
        predicates = []
        if uni_ids:
            predicates.append(FacultyProposal.university_id.in_(uni_ids))
        if fac_ids:
            faculty_scope_university_ids = select(Faculty.university_id).where(Faculty.id.in_(fac_ids))
            predicates.append(FacultyProposal.university_id.in_(faculty_scope_university_ids))
        result = await self.session.execute(statement.where(or_(*predicates)))
        return list(result.scalars().all())

    async def _list_pending_subject_proposals(self, actor: User):
        statement = (
            select(SubjectProposal)
            .options(selectinload(SubjectProposal.creator))
            .join(Faculty, Faculty.id == SubjectProposal.faculty_id)
            .where(SubjectProposal.status == ProposalStatus.PENDING)
            .order_by(SubjectProposal.created_at.asc())
        )
        if actor.role.value == "admin":
            result = await self.session.execute(statement)
            return list(result.scalars().all())
        uni_ids, fac_ids, sub_ids = await self._scope_ids(actor.id)
        predicates = []
        if uni_ids:
            predicates.append(Faculty.university_id.in_(uni_ids))
        if fac_ids:
            predicates.append(SubjectProposal.faculty_id.in_(fac_ids))
        if sub_ids:
            predicates.append(SubjectProposal.faculty_id.in_(select(Subject.faculty_id).where(Subject.id.in_(sub_ids))))
        if not predicates:
            return []
        result = await self.session.execute(statement.where(or_(*predicates)))
        return list(result.scalars().all())

    async def _assert_faculty_proposal_scope(self, actor: User, proposal: FacultyProposal) -> None:
        if actor.role.value == "admin":
            return
        uni_ids, _, _ = await self._scope_ids(actor.id)
        if proposal.university_id not in uni_ids:
            raise PermissionDenied("Proposal is outside your moderation scope")

    async def _assert_subject_proposal_scope(self, actor: User, proposal: SubjectProposal) -> None:
        if actor.role.value == "admin":
            return
        faculty = await self.session.get(Faculty, proposal.faculty_id)
        if not faculty:
            raise ResourceNotFound("Faculty not found")
        uni_ids, fac_ids, sub_ids = await self._scope_ids(actor.id)
        allowed = faculty.university_id in uni_ids or proposal.faculty_id in fac_ids
        if not allowed and sub_ids:
            subject_match = await self.session.execute(
                select(Subject.id).where(Subject.id.in_(sub_ids), Subject.faculty_id == proposal.faculty_id)
            )
            allowed = subject_match.scalar_one_or_none() is not None
        if not allowed:
            raise PermissionDenied("Proposal is outside your moderation scope")

    async def _scope_ids(self, user_id: str) -> tuple[set[str], set[str], set[str]]:
        uni_ids = set(
            (
                await self.session.execute(
                    select(ModeratorUniversityScope.university_id).where(ModeratorUniversityScope.user_id == user_id)
                )
            ).scalars().all()
        )
        fac_ids = set(
            (
                await self.session.execute(
                    select(ModeratorFacultyScope.faculty_id).where(ModeratorFacultyScope.user_id == user_id)
                )
            ).scalars().all()
        )
        sub_ids = set(
            (
                await self.session.execute(
                    select(ModeratorSubjectScope.subject_id).where(ModeratorSubjectScope.user_id == user_id)
                )
            ).scalars().all()
        )
        return uni_ids, fac_ids, sub_ids

    async def _log(
        self,
        entity_type: ProposalEntityType,
        entity_id: str,
        action: str,
        actor_id: str,
        note: str | None = None,
    ) -> None:
        self.session.add(
            CatalogProposalLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_id=actor_id,
                note=note,
            )
        )

    @staticmethod
    def _require_admin(actor: User) -> None:
        if actor.role.value != "admin":
            raise PermissionDenied("Admin access required")

    async def _ensure_university_name_available(self, name: str) -> None:
        result = await self.session.execute(
            select(University.id).where(func.lower(func.trim(University.name)) == self._normalize_name(name))
        )
        if result.scalar_one_or_none():
            raise ConflictError("University already exists")

    async def _ensure_university_slug_available(self, slug: str) -> None:
        result = await self.session.execute(select(University.id).where(University.slug == slug))
        if result.scalar_one_or_none():
            raise ConflictError("University already exists")

    async def _ensure_faculty_name_available(self, university_id: str, name: str) -> None:
        result = await self.session.execute(
            select(Faculty.id).where(
                Faculty.university_id == university_id,
                func.lower(func.trim(Faculty.name)) == self._normalize_name(name),
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Faculty already exists in this university")

    async def _ensure_faculty_slug_available(self, university_id: str, slug: str) -> None:
        result = await self.session.execute(
            select(Faculty.id).where(Faculty.university_id == university_id, Faculty.slug == slug)
        )
        if result.scalar_one_or_none():
            raise ConflictError("Faculty already exists in this university")

    async def _ensure_subject_name_available(self, faculty_id: str, name: str, semester: int) -> None:
        result = await self.session.execute(
            select(Subject.id).where(
                Subject.faculty_id == faculty_id,
                Subject.semester == semester,
                func.lower(func.trim(Subject.name)) == self._normalize_name(name),
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Subject already exists in this faculty and semester")

    async def _ensure_subject_slug_available(self, faculty_id: str, slug: str, semester: int) -> None:
        result = await self.session.execute(
            select(Subject.id).where(
                Subject.faculty_id == faculty_id,
                Subject.slug == slug,
                Subject.semester == semester,
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Subject already exists in this faculty and semester")

    async def _ensure_pending_faculty_proposal_name_available(self, university_id: str, name: str) -> None:
        result = await self.session.execute(
            select(FacultyProposal.id).where(
                FacultyProposal.university_id == university_id,
                FacultyProposal.status == ProposalStatus.PENDING,
                func.lower(func.trim(FacultyProposal.proposed_name)) == self._normalize_name(name),
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Faculty proposal with this name is already pending in the university")

    async def _ensure_pending_subject_proposal_name_available(
        self,
        faculty_id: str,
        name: str,
        semester: int,
    ) -> None:
        result = await self.session.execute(
            select(SubjectProposal.id).where(
                SubjectProposal.faculty_id == faculty_id,
                SubjectProposal.status == ProposalStatus.PENDING,
                SubjectProposal.proposed_semester == semester,
                func.lower(func.trim(SubjectProposal.proposed_name)) == self._normalize_name(name),
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("Subject proposal with this name is already pending in the faculty and semester")

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()
