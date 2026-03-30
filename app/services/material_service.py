from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import ConflictError, PermissionDenied, ResourceNotFound, ValidationAppError
from app.enums.file_kind import FileKind
from app.enums.material_status import MaterialStatus
from app.enums.report_status import ReportStatus
from app.enums.review_action import ReviewAction
from app.models.material import Material
from app.models.material_file import MaterialFile
from app.models.material_rating import MaterialRating
from app.models.material_report import MaterialReport
from app.models.material_review_log import MaterialReviewLog
from app.models.user import User
from app.repositories.material_file_repository import MaterialFileRepository
from app.repositories.material_repository import MaterialRepository
from app.repositories.material_review_log_repository import MaterialReviewLogRepository
from app.repositories.subject_repository import SubjectRepository
from app.schemas.material import MaterialCreate, MaterialListQuery, MaterialReportCreate, MaterialUpdate
from app.services.audit_service import AuditService
from app.services.storage_service import StorageService
from app.utils.files import PREVIEWABLE_EXTENSIONS


class MaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.materials = MaterialRepository(session)
        self.files = MaterialFileRepository(session)
        self.subjects = SubjectRepository(session)
        self.logs = MaterialReviewLogRepository(session)
        self.storage = StorageService()
        self.audit = AuditService(session)
        self.cache = get_cache()

    async def create_draft(self, payload: MaterialCreate, user: User) -> Material:
        await self._ensure_subject(payload.subject_id)
        material = Material(
            title=payload.title,
            description=payload.description,
            material_type=payload.material_type,
            subject_id=payload.subject_id,
            uploaded_by=user.id,
            cover_file_id=payload.cover_file_id,
            primary_file_id=payload.primary_file_id,
        )
        await self.materials.create(material)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def attach_files(
        self,
        material_id: str,
        user: User,
        uploads: list[UploadFile],
        file_orders: list[int],
    ) -> list[MaterialFile]:
        material = await self._get_owned_material(material_id, user.id)
        if material.status != MaterialStatus.DRAFT:
            raise ConflictError("Files can only be attached to draft materials")
        if len(uploads) != len(file_orders):
            raise ValidationAppError("Each file must have a file_order")
        if len(uploads) > self.settings.upload_max_file_count:
            raise ValidationAppError("Too many files")

        total_size = material.total_size
        storage_keys: list[str] = []
        normalized_orders = file_orders[:]
        if len(set(normalized_orders)) != len(normalized_orders):
            normalized_orders = list(range(material.file_count, material.file_count + len(file_orders)))

        try:
            stored_files = []
            for upload in uploads:
                stored = await self.storage.save(
                    upload,
                    material.id,
                    max_file_size=self.settings.upload_max_file_size,
                )
                total_size += stored.file_size
                if total_size > self.settings.upload_max_total_size:
                    self.storage.delete(stored.storage_key)
                    raise ValidationAppError("Total upload size exceeded")
                stored_files.append(stored)
                storage_keys.append(stored.storage_key)
            entities: list[MaterialFile] = []
            for index, (upload, stored) in enumerate(zip(uploads, stored_files)):
                entities.append(
                    MaterialFile(
                        material_id=material.id,
                        storage_key=stored.storage_key,
                        original_filename=upload.filename or stored.storage_key,
                        mime_type=stored.mime_type,
                        file_size=stored.file_size,
                        file_ext=stored.file_ext,
                        file_kind=stored.file_kind,
                        file_order=normalized_orders[index],
                        checksum_hash=stored.checksum_hash,
                        is_previewable=stored.file_kind in {FileKind.IMAGE, FileKind.DOCUMENT}
                        and stored.file_ext in PREVIEWABLE_EXTENSIONS,
                    )
                )

            await self.files.create_many(entities)
            await self.session.execute(
                update(Material)
                .where(Material.id == material.id)
                .values(
                    file_count=Material.file_count + len(entities),
                    total_size=Material.total_size + sum(item.file_size for item in entities),
                )
            )
            await self.session.commit()
            await self._invalidate_material_caches()
            return entities
        except Exception:
            await self.session.rollback()
            self.storage.delete_many(storage_keys)
            raise

    async def submit(self, material_id: str, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        action = ReviewAction.SUBMITTED if material.status == MaterialStatus.DRAFT else ReviewAction.RESUBMITTED
        if material.status not in {MaterialStatus.DRAFT, MaterialStatus.REJECTED}:
            raise ConflictError("Only draft or rejected materials can be submitted")
        if material.file_count < 1:
            raise ValidationAppError("At least one file is required before submission")
        material.status = MaterialStatus.PENDING_REVIEW
        material.submitted_at = datetime.now(UTC)
        await self.logs.create(MaterialReviewLog(material_id=material.id, action=action, actor_id=user.id))
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def withdraw(self, material_id: str, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        if material.status != MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Only pending materials can be withdrawn")
        material.status = MaterialStatus.DRAFT
        await self.logs.create(
            MaterialReviewLog(material_id=material.id, action=ReviewAction.WITHDRAWN, actor_id=user.id)
        )
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def update_material(self, material_id: str, payload: MaterialUpdate, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        if payload.subject_id:
            await self._ensure_subject(payload.subject_id)
        if material.status == MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Pending review material must be withdrawn before editing")
        if material.status == MaterialStatus.APPROVED:
            material.status = MaterialStatus.PENDING_REVIEW
            material.submitted_at = datetime.now(UTC)
            await self.logs.create(
                MaterialReviewLog(material_id=material.id, action=ReviewAction.RESUBMITTED, actor_id=user.id)
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(material, field, value)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def delete_material(self, material_id: str, user: User) -> None:
        material = await self._get_owned_material(material_id, user.id)
        material.mark_deleted()
        await self.session.commit()
        await self._invalidate_material_caches()

    async def get_material_for_view(self, material_id: str, user: User | None = None) -> Material:
        material = await self.materials.get(material_id)
        if not material or material.deleted_at is not None:
            raise ResourceNotFound("Material not found")
        if material.status == MaterialStatus.APPROVED:
            return material
        if user and user.role.value in {"admin", "moderator"}:
            return material
        if not user or material.uploaded_by != user.id:
            raise PermissionDenied("You do not have access to this material")
        return material

    async def list_for_user(self, user: User) -> list[Material]:
        return await self.materials.list_for_owner(user.id)

    async def list_public(self, query: MaterialListQuery):
        if not query.status:
            query.status = MaterialStatus.APPROVED
        statement = self.materials.build_filtered_query()
        statement = self.materials.apply_filters(statement, query)
        return await self.materials.list_filtered(statement, query.page, query.page_size)

    async def report_material(self, material_id: str, payload: MaterialReportCreate, user: User) -> None:
        material = await self.materials.get(material_id)
        if not material or material.status != MaterialStatus.APPROVED:
            raise ResourceNotFound("Material not found")
        report = MaterialReport(
            material_id=material.id,
            reporter_id=user.id,
            reason=payload.reason,
            details=payload.details,
            status=ReportStatus.OPEN,
        )
        self.session.add(report)
        await self.logs.create(
            MaterialReviewLog(
                material_id=material.id,
                action=ReviewAction.REPORTED,
                actor_id=user.id,
                note=payload.details,
                reason=payload.reason,
            )
        )
        await self.audit.log("material_reported", "material_report", user, material.id, payload.reason)
        await self.session.commit()

    async def prepare_download(self, material_id: str, file_id: str | None, user: User | None = None) -> Path:
        material = await self.get_material_for_view(material_id, user)
        file_entry = (
            await self.files.get(file_id)
            if file_id
            else await self.files.get(material.primary_file_id or material.cover_file_id or material.files[0].id)
        )
        if not file_entry or file_entry.material_id != material.id:
            raise ResourceNotFound("Material file not found")
        if not self.storage.exists(file_entry.storage_key):
            raise ResourceNotFound("Stored file not found")
        await self.session.execute(
            update(Material)
            .where(Material.id == material.id)
            .values(download_count=Material.download_count + 1)
        )
        await self.session.commit()
        await self.cache.invalidate("materials:stats_summary")
        await self.cache.invalidate("materials:trending_ids")
        return self.storage.open_for_download(file_entry.storage_key)

    async def prepare_preview(self, material_id: str, file_id: str, user: User | None = None) -> Path:
        material = await self.get_material_for_view(material_id, user)
        file_entry = await self.files.get(file_id)
        if not file_entry or file_entry.material_id != material.id:
            raise ResourceNotFound("Material file not found")
        if not file_entry.is_previewable:
            raise PermissionDenied("File is not previewable")
        return self.storage.open_for_download(file_entry.storage_key)

    async def list_related(self, material_id: str) -> list[Material]:
        material = await self.materials.get(material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        query = MaterialListQuery(subject_id=material.subject_id, page=1, page_size=6)
        items, _ = await self.list_public(query)
        return [item for item in items if item.id != material_id][:5]

    async def list_resources(self, material_id: str) -> list[MaterialFile]:
        material = await self.materials.get(material_id)
        if not material:
            raise ResourceNotFound("Material not found")
        return material.files

    async def list_featured(self) -> list[Material]:
        query = MaterialListQuery(sort="download_count_desc", page=1, page_size=10)
        items, _ = await self.list_public(query)
        return items

    async def list_trending(self) -> list[Material]:
        cached_ids = await self.cache.get("materials:trending_ids")
        if cached_ids:
            cached_items = await self.materials.get_many(cached_ids)
            if len(cached_items) == len(cached_ids):
                return cached_items
        statement = (
            self.materials.build_filtered_query()
            .where(Material.status == MaterialStatus.APPROVED)
            .order_by(Material.reviewed_at.desc().nullslast(), Material.download_count.desc())
            .limit(10)
        )
        result = await self.session.execute(statement)
        items = list(result.scalars().all())
        await self.cache.set(
            "materials:trending_ids",
            [item.id for item in items],
            self.settings.cache_ttl_trending_seconds,
        )
        return items

    async def stats_summary(self) -> dict:
        cached_summary = await self.cache.get("materials:stats_summary")
        if cached_summary is not None:
            return cached_summary
        total = (await self.session.execute(select(func.count(Material.id)))).scalar_one()
        approved = (
            await self.session.execute(
                select(func.count(Material.id)).where(Material.status == MaterialStatus.APPROVED)
            )
        ).scalar_one()
        pending = (
            await self.session.execute(
                select(func.count(Material.id)).where(Material.status == MaterialStatus.PENDING_REVIEW)
            )
        ).scalar_one()
        downloads = (await self.session.execute(select(func.coalesce(func.sum(Material.download_count), 0)))).scalar_one()
        summary = {
            "total_materials": total,
            "approved_materials": approved,
            "pending_materials": pending,
            "total_downloads": downloads,
        }
        await self.cache.set("materials:stats_summary", summary, self.settings.cache_ttl_stats_seconds)
        return summary

    async def get_rating_snapshot(self, material_ids: list[str]) -> dict[str, tuple[float, int]]:
        if not material_ids:
            return {}
        result = await self.session.execute(
            select(
                MaterialRating.material_id,
                func.avg(MaterialRating.value),
                func.count(MaterialRating.id),
            )
            .where(MaterialRating.material_id.in_(material_ids))
            .group_by(MaterialRating.material_id)
        )
        return {row[0]: (float(row[1] or 0.0), int(row[2] or 0)) for row in result.all()}

    async def cleanup_stale_drafts(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=7)
        statement = self.materials.build_filtered_query().where(
            Material.status == MaterialStatus.DRAFT,
            Material.updated_at < cutoff,
        )
        drafts, _ = await self.materials.list_filtered(statement, 1, 10_000)
        count = 0
        for draft in drafts:
            draft.mark_deleted()
            count += 1
        await self.session.commit()
        if count:
            await self._invalidate_material_caches()
        return count

    async def _get_owned_material(self, material_id: str, owner_id: str) -> Material:
        material = await self.materials.get(material_id)
        if not material or material.deleted_at is not None:
            raise ResourceNotFound("Material not found")
        if material.uploaded_by != owner_id:
            raise PermissionDenied("You do not own this material")
        return material

    async def _ensure_subject(self, subject_id: str) -> None:
        if not await self.subjects.get(subject_id):
            raise ResourceNotFound("Subject not found")

    async def _invalidate_material_caches(self) -> None:
        await self.cache.invalidate("materials:stats_summary")
        await self.cache.invalidate("materials:trending_ids")
        await self.cache.invalidate_prefix("admin:dashboard_")
