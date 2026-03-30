from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.exceptions import ConflictError, PermissionDenied, ResourceNotFound
from app.enums.material_status import MaterialStatus
from app.enums.review_action import ReviewAction
from app.models.faculty import Faculty
from app.models.material import Material
from app.models.material_review_log import MaterialReviewLog
from app.models.moderator_scope import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.models.subject import Subject
from app.models.user import User
from app.repositories.material_repository import MaterialRepository
from app.repositories.material_review_log_repository import MaterialReviewLogRepository
from app.repositories.subject_repository import SubjectRepository
from app.schemas.moderation import MoveSubjectRequest, RejectRequest
from app.services.audit_service import AuditService


class ModerationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.materials = MaterialRepository(session)
        self.logs = MaterialReviewLogRepository(session)
        self.subjects = SubjectRepository(session)
        self.audit = AuditService(session)
        self.cache = get_cache()

    async def list_pending(self, actor: User) -> list[Material]:
        statement = self.materials.build_filtered_query().where(Material.status == MaterialStatus.PENDING_REVIEW)
        statement = await self._apply_scope(statement, actor)
        materials, _ = await self.materials.list_filtered(statement.order_by(Material.created_at.asc()), 1, 1000)
        return materials

    async def approve(self, material_id: str, actor: User) -> Material:
        material = await self._get_scoped_material(material_id, actor)
        if material.status != MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Only pending materials can be approved")
        if material.file_count < 1:
            raise ConflictError("Material must have files before approval")
        material.status = MaterialStatus.APPROVED
        material.approved_by = actor.id
        material.last_reviewed_by = actor.id
        material.reviewed_at = datetime.now(UTC)
        material.rejected_reason = None
        await self.logs.create(
            MaterialReviewLog(material_id=material.id, action=ReviewAction.APPROVED, actor_id=actor.id)
        )
        await self.audit.log("material_approved", "material", actor, material.id)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def reject(self, material_id: str, payload: RejectRequest, actor: User) -> Material:
        material = await self._get_scoped_material(material_id, actor)
        if material.status != MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Only pending materials can be rejected")
        material.status = MaterialStatus.REJECTED
        material.rejected_reason = payload.reason
        material.last_reviewed_by = actor.id
        material.reviewed_at = datetime.now(UTC)
        await self.logs.create(
            MaterialReviewLog(
                material_id=material.id,
                action=ReviewAction.REJECTED,
                actor_id=actor.id,
                note=payload.note,
                reason=payload.reason.value,
            )
        )
        await self.audit.log("material_rejected", "material", actor, material.id, payload.reason.value)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def move_subject(self, material_id: str, payload: MoveSubjectRequest, actor: User) -> Material:
        material = await self._get_scoped_material(material_id, actor)
        if not await self.subjects.get(payload.subject_id):
            raise ResourceNotFound("Subject not found")
        material.subject_id = payload.subject_id
        material.last_reviewed_by = actor.id
        material.reviewed_at = datetime.now(UTC)
        await self.logs.create(
            MaterialReviewLog(
                material_id=material.id,
                action=ReviewAction.MOVED_SUBJECT,
                actor_id=actor.id,
                note=payload.note,
            )
        )
        await self.audit.log("material_subject_moved", "material", actor, material.id, payload.subject_id)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def request_revision(self, material_id: str, payload: RejectRequest, actor: User) -> Material:
        material = await self._get_scoped_material(material_id, actor)
        if material.status != MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Only pending materials can request revision")
        material.status = MaterialStatus.REJECTED
        material.rejected_reason = payload.reason
        material.last_reviewed_by = actor.id
        material.reviewed_at = datetime.now(UTC)
        await self.logs.create(
            MaterialReviewLog(
                material_id=material.id,
                action=ReviewAction.REQUESTED_REVISION,
                actor_id=actor.id,
                note=payload.note,
                reason=payload.reason.value,
            )
        )
        await self.audit.log("material_revision_requested", "material", actor, material.id, payload.reason.value)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def history(self, material_id: str, actor: User) -> list[MaterialReviewLog]:
        await self._get_scoped_material(material_id, actor)
        result = await self.session.execute(
            select(MaterialReviewLog)
            .where(MaterialReviewLog.material_id == material_id)
            .order_by(MaterialReviewLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def context(self, material_id: str, actor: User) -> dict:
        material = await self._get_scoped_material(material_id, actor)
        history = await self.history(material_id, actor)
        return {
            "material_id": material.id,
            "title": material.title,
            "status": material.status.value,
            "rejected_reason": material.rejected_reason.value if material.rejected_reason else None,
            "history": [
                {
                    "id": log.id,
                    "action": log.action.value,
                    "actor_id": log.actor_id,
                    "note": log.note,
                    "reason": log.reason,
                    "created_at": log.created_at,
                }
                for log in history
            ],
        }

    async def _get_scoped_material(self, material_id: str, actor: User) -> Material:
        material = await self.materials.get(material_id)
        if not material or material.deleted_at is not None:
            raise ResourceNotFound("Material not found")
        await self._assert_scope(actor, material)
        return material

    async def _apply_scope(self, statement, actor: User):
        if actor.role.value == "admin":
            return statement

        uni_stmt = select(ModeratorUniversityScope.university_id).where(ModeratorUniversityScope.user_id == actor.id)
        fac_stmt = select(ModeratorFacultyScope.faculty_id).where(ModeratorFacultyScope.user_id == actor.id)
        sub_stmt = select(ModeratorSubjectScope.subject_id).where(ModeratorSubjectScope.user_id == actor.id)

        uni_ids = set((await self.session.execute(uni_stmt)).scalars().all())
        fac_ids = set((await self.session.execute(fac_stmt)).scalars().all())
        sub_ids = set((await self.session.execute(sub_stmt)).scalars().all())

        predicates = []
        if uni_ids:
            predicates.append(Faculty.university_id.in_(uni_ids))
        if fac_ids:
            predicates.append(Subject.faculty_id.in_(fac_ids))
        if sub_ids:
            predicates.append(Material.subject_id.in_(sub_ids))
        if not predicates:
            statement = statement.where(Material.id == "__none__")
        else:
            statement = statement.where(or_(*predicates))
        return statement

    async def _assert_scope(self, actor: User, material: Material) -> None:
        if actor.role.value == "admin":
            return
        subject = await self.subjects.get(material.subject_id)
        if not subject:
            raise ResourceNotFound("Subject not found")
        faculty = subject.faculty
        if not faculty:
            faculty = (
                await self.session.execute(select(Faculty).where(Faculty.id == subject.faculty_id))
            ).scalar_one_or_none()
            if not faculty:
                raise ResourceNotFound("Faculty not found")
        uni_ids = set(
            (
                await self.session.execute(
                    select(ModeratorUniversityScope.university_id).where(ModeratorUniversityScope.user_id == actor.id)
                )
            ).scalars().all()
        )
        fac_ids = set(
            (
                await self.session.execute(
                    select(ModeratorFacultyScope.faculty_id).where(ModeratorFacultyScope.user_id == actor.id)
                )
            ).scalars().all()
        )
        sub_ids = set(
            (
                await self.session.execute(
                    select(ModeratorSubjectScope.subject_id).where(ModeratorSubjectScope.user_id == actor.id)
                )
            ).scalars().all()
        )
        allowed = subject.id in sub_ids or subject.faculty_id in fac_ids or faculty.university_id in uni_ids
        if not allowed:
            raise PermissionDenied("Material is outside your moderation scope")

    async def _invalidate_material_caches(self) -> None:
        await self.cache.invalidate("materials:stats_summary")
        await self.cache.invalidate("materials:trending_ids")
        await self.cache.invalidate_prefix("admin:dashboard_")
