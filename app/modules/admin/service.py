from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import get_cache
from app.core.exceptions import ResourceNotFound, ValidationAppError
from app.modules.audit.models import AuditLog
from app.modules.admin.scope_models import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.modules.materials.enums import MaterialStatus, ReportStatus
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.materials.models import Material
from app.modules.notifications.models import Notification
from app.modules.users.models import User
from app.modules.admin.repository import ModeratorScopeRepository
from app.modules.materials.models import MaterialReport
from app.modules.users.enums import UserRole
from app.modules.users.repository import UserRepository
from app.modules.admin.schemas import ModeratorScopeCreate
from app.modules.audit.service import AuditService


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.scopes = ModeratorScopeRepository(session)
        self.audit = AuditService(session)
        self.cache = get_cache()

    async def update_user_role(self, user_id: str, role: UserRole):
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ResourceNotFound("User not found")
        user.role = role
        await self.audit.log("user_role_updated", "user", None, user.id, role.value)
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return user

    async def update_user(self, user_id: str, payload: dict):
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ResourceNotFound("User not found")
        for field, value in payload.items():
            setattr(user, field, value)
        await self.audit.log("user_updated", "user", None, user.id)
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return user

    async def set_user_status(self, user_id: str, is_active: bool):
        return await self.update_user(user_id, {"is_active": is_active})

    async def verify_user(self, user_id: str, is_verified: bool = True):
        return await self.update_user(user_id, {"is_verified": is_verified})

    async def list_users(
        self,
        q: str | None = None,
        role: str | None = None,
        status: bool | None = None,
        university_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        return await self.users.list_filtered(q, role, status, university_id, page, page_size)

    async def get_user_detail(self, user_id: str) -> User:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ResourceNotFound("User not found")
        return user

    async def add_moderator_scope(self, user_id: str, payload: ModeratorScopeCreate):
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ResourceNotFound("User not found")
        provided = [payload.university_id, payload.faculty_id, payload.subject_id]
        if len([item for item in provided if item]) != 1:
            raise ValidationAppError("Provide exactly one scope target")
        scope = await self.scopes.add_scope(
            user_id=user_id,
            university_id=payload.university_id,
            faculty_id=payload.faculty_id,
            subject_id=payload.subject_id,
        )
        if user.role == UserRole.STUDENT:
            user.role = UserRole.MODERATOR
        await self.audit.log("moderator_scope_added", "user_scope", None, user_id)
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return {"message": "Moderator scope assigned", "scope_id": scope.id}

    async def list_moderator_scopes(self, user_id: str) -> list[dict]:
        rows = []
        for model, entity, label in (
            (ModeratorUniversityScope, University, "university"),
            (ModeratorFacultyScope, Faculty, "faculty"),
            (ModeratorSubjectScope, Subject, "subject"),
        ):
            stmt = (
                select(model, entity)
                .join(entity, getattr(model, f"{label}_id") == entity.id)
                .where(model.user_id == user_id)
            )
            result = await self.session.execute(stmt)
            for scope, linked in result.all():
                rows.append({"id": scope.id, "scope_type": label, "scope_id": linked.id, "name": linked.name})
        return rows

    async def delete_moderator_scope(self, user_id: str, scope_id: str) -> None:
        deleted = False
        for model in (ModeratorUniversityScope, ModeratorFacultyScope, ModeratorSubjectScope):
            scope = await self.session.get(model, scope_id)
            if scope and scope.user_id == user_id:
                await self.session.delete(scope)
                deleted = True
                break
        if not deleted:
            raise ResourceNotFound("Moderator scope not found")
        await self.audit.log("moderator_scope_deleted", "user_scope", None, user_id, scope_id)
        await self.session.commit()
        await self._invalidate_dashboard_cache()

    async def list_all_moderator_scopes(self) -> list[dict]:
        result = []
        users, _ = await self.list_users(page=1, page_size=500)
        for user in users:
            scopes = await self.list_moderator_scopes(user.id)
            for scope in scopes:
                result.append({"user_id": user.id, "user_name": user.full_name, **scope})
        return result

    async def list_reports(self, page: int = 1, page_size: int = 20, status: ReportStatus | None = None):
        stmt = (
            select(MaterialReport)
            .options(
                selectinload(MaterialReport.reporter).selectinload(User.university),
                selectinload(MaterialReport.material),
            )
            .order_by(MaterialReport.created_at.desc())
        )
        if status:
            stmt = stmt.where(MaterialReport.status == status)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total

    async def get_report(self, report_id: str) -> MaterialReport:
        result = await self.session.execute(
            select(MaterialReport)
            .where(MaterialReport.id == report_id)
            .options(
                selectinload(MaterialReport.reporter).selectinload(User.university),
                selectinload(MaterialReport.material),
            )
        )
        report = result.scalar_one_or_none()
        if not report:
            raise ResourceNotFound("Report not found")
        return report

    async def update_report(self, report_id: str, payload: dict) -> MaterialReport:
        report = await self.get_report(report_id)
        for field, value in payload.items():
            setattr(report, field, value)
        await self.audit.log("report_updated", "material_report", None, report.id)
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return await self.get_report(report_id)

    async def resolve_report(self, report_id: str, resolution_note: str | None = None) -> MaterialReport:
        report = await self.get_report(report_id)
        report.status = ReportStatus.RESOLVED
        report.resolution_note = resolution_note
        report.reviewed_at = datetime.now(UTC)
        await self.audit.log("report_resolved", "material_report", None, report.id, resolution_note)
        self.session.add(
            Notification(
                user_id=report.reporter_id,
                title="Your report was resolved",
                body=f"Report for material {report.material_id} has been resolved.",
            )
        )
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return await self.get_report(report_id)

    async def dismiss_report(self, report_id: str, resolution_note: str | None = None) -> MaterialReport:
        report = await self.get_report(report_id)
        report.status = ReportStatus.DISMISSED
        report.resolution_note = resolution_note
        report.reviewed_at = datetime.now(UTC)
        await self.audit.log("report_dismissed", "material_report", None, report.id, resolution_note)
        await self.session.commit()
        await self._invalidate_dashboard_cache()
        return await self.get_report(report_id)

    async def list_audit_logs(
        self,
        actor_id: str | None = None,
        entity: str | None = None,
        action: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        stmt = select(AuditLog).options(selectinload(AuditLog.actor).selectinload(User.university))
        if actor_id:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if entity:
            stmt = stmt.where(AuditLog.entity == entity)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.created_at.desc())
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total

    async def dashboard_summary(self) -> dict:
        cached_summary = await self.cache.get("admin:dashboard_summary")
        if cached_summary is not None:
            return cached_summary
        total_materials = (await self.session.execute(select(func.count(Material.id)))).scalar_one()
        pending_materials = (
            await self.session.execute(
                select(func.count(Material.id)).where(Material.status == MaterialStatus.PENDING_REVIEW)
            )
        ).scalar_one()
        reports_open = (
            await self.session.execute(select(func.count(MaterialReport.id)).where(MaterialReport.status == ReportStatus.OPEN))
        ).scalar_one()
        users_by_role_rows = await self.session.execute(select(User.role, func.count(User.id)).group_by(User.role))
        users_by_role = {role.value: count for role, count in users_by_role_rows.all()}
        summary = {
            "total_materials": total_materials,
            "pending_moderation": pending_materials,
            "open_reports": reports_open,
            "users_by_role": users_by_role,
        }
        await self.cache.set("admin:dashboard_summary", summary, 300)
        return summary

    async def dashboard_charts(self) -> dict:
        cached_charts = await self.cache.get("admin:dashboard_charts")
        if cached_charts is not None:
            return cached_charts
        top_universities = await self.session.execute(
            select(University.name, func.count(Material.id))
            .join(Faculty, Faculty.university_id == University.id)
            .join(Subject, Subject.faculty_id == Faculty.id)
            .join(Material, Material.subject_id == Subject.id)
            .group_by(University.name)
            .order_by(func.count(Material.id).desc())
            .limit(5)
        )
        top_material_types = await self.session.execute(
            select(Material.material_type, func.count(Material.id))
            .group_by(Material.material_type)
            .order_by(func.count(Material.id).desc())
        )
        charts = {
            "top_universities": [
                {"label": label, "value": value} for label, value in top_universities.all()
            ],
            "top_material_types": [
                {"label": label.value if hasattr(label, "value") else str(label), "value": value}
                for label, value in top_material_types.all()
            ],
        }
        await self.cache.set("admin:dashboard_charts", charts, 300)
        return charts

    async def _invalidate_dashboard_cache(self) -> None:
        await self.cache.invalidate_prefix("admin:dashboard_")
