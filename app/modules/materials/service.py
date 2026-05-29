from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader, PdfWriter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDenied, ResourceNotFound, ValidationAppError
from app.modules.audit.service import AuditService
from app.infrastructure.storage.service import StorageDownload, StorageService
from app.modules.catalog.repositories import SubjectRepository
from app.modules.community.models import MaterialRating
from app.modules.materials.enums import FileKind, MaterialStatus, ReportStatus, ReviewAction
from app.modules.materials.models import Material, MaterialFile, MaterialReport, MaterialReviewLog, MaterialDownload
from app.modules.materials.repositories import MaterialFileRepository, MaterialRepository, MaterialReviewLogRepository
from app.modules.materials.schemas import MaterialCreate, MaterialListQuery, MaterialReportCreate, MaterialUpdate
from app.modules.tags.models import Tag
from app.modules.telegram.event_service import TelegramEventService
from app.modules.users.models import User
from app.utils.files import PREVIEWABLE_EXTENSIONS
from app.utils.slug import slugify

PDF_PREVIEW_PAGE_LIMIT = 2


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
            slug=await self._generate_unique_slug(payload.title),
            description=payload.description,
            material_type=payload.material_type,
            subject_id=payload.subject_id,
            semesters=payload.semesters,
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
                    await self.storage.delete(stored.storage_key)
                    raise ValidationAppError("Total upload size exceeded")
                stored_files.append(stored)
                storage_keys.append(stored.storage_key)
            entities: list[MaterialFile] = []
            for index, (upload, stored) in enumerate(zip(uploads, stored_files)):
                preview_storage_key = None
                preview_page_count = None
                if stored.file_ext == "pdf":
                    preview_storage_key, preview_page_count = await self._build_pdf_preview(
                        material.id,
                        stored.storage_key,
                    )
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
                        is_previewable=stored.file_ext in PREVIEWABLE_EXTENSIONS,
                        preview_storage_key=preview_storage_key,
                        preview_page_count=preview_page_count,
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
            await self.storage.delete_many(storage_keys)
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
        review_log = await self.logs.create(MaterialReviewLog(material_id=material.id, action=action, actor_id=user.id))
        await TelegramEventService(self.session).enqueue_material_submitted_events(
            material,
            event_id=review_log.id,
        )
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
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)
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

    async def get_material_for_view(
        self,
        identifier: str,
        user: User | None = None,
        lookup_field: str = "id",
    ) -> Material:
        material = await self._get_material(identifier, lookup_field)
        if not material or material.deleted_at is not None:
            raise ResourceNotFound("Material not found")
        if material.status == MaterialStatus.APPROVED:
            return material
        if user and user.role.value in {"admin", "moderator"}:
            return material
        if not user or material.uploaded_by != user.id:
            raise PermissionDenied("You do not have access to this material")
        return material

    async def get_material_by_slug_for_view(self, slug: str, user: User | None = None) -> Material:
        return await self.get_material_for_view(slug, user, lookup_field="slug")

    async def list_for_user(self, user: User) -> list[Material]:
        return await self.materials.list_for_owner(user.id)

    async def list_public(self, query: MaterialListQuery):
        query.status = MaterialStatus.APPROVED
        statement = self.materials.build_filtered_query()
        statement = self.materials.apply_filters(statement, query)
        return await self.materials.list_filtered(statement, query.page, query.page_size)

    async def attach_tag(self, material_id: str, tag_id: str, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            raise ResourceNotFound("Tag not found")
        if any(existing.id == tag.id for existing in material.tags):
            return material
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)
        material.tags.append(tag)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def detach_tag(self, material_id: str, tag_id: str, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        tag = next((item for item in material.tags if item.id == tag_id), None)
        if not tag:
            raise ResourceNotFound("Tag not attached to material")
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)
        material.tags.remove(tag)
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

    async def delete_file(self, material_id: str, file_id: str, user: User) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        files = await self.files.list_by_material(material.id)
        target = next((item for item in files if item.id == file_id), None)
        if not target:
            raise ResourceNotFound("Material file not found")
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)

        remaining = [item for item in files if item.id != target.id]
        for index, item in enumerate(remaining):
            item.file_order = index
        fallback_id = remaining[0].id if remaining else None
        if material.cover_file_id == target.id:
            material.cover_file_id = fallback_id
        if material.primary_file_id == target.id:
            material.primary_file_id = fallback_id

        material.file_count = max(0, material.file_count - 1)
        material.total_size = max(0, material.total_size - target.file_size)
        refreshed_material_id = material.id
        await self.session.delete(target)
        await self.session.commit()
        self.session.expire_all()
        await self._best_effort_delete_storage_keys(
            [key for key in [target.storage_key, target.preview_storage_key] if key]
        )
        await self._invalidate_material_caches()
        return await self.materials.get(refreshed_material_id)

    async def reorder_files(self, material_id: str, file_ids: list[str], user: User) -> list[MaterialFile]:
        material = await self._get_owned_material(material_id, user.id)
        files = await self.files.list_by_material(material.id)
        existing_ids = [item.id for item in files]
        if len(file_ids) != len(existing_ids) or set(file_ids) != set(existing_ids):
            raise ValidationAppError("file_ids must include every existing material file exactly once")
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)
        file_map = {item.id: item for item in files}
        for index, file_id in enumerate(file_ids):
            file_map[file_id].file_order = index
        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.files.list_by_material(material.id)

    async def update_file_selection(
        self,
        material_id: str,
        file_id: str,
        cover: bool | None,
        primary: bool | None,
        user: User,
    ) -> Material:
        material = await self._get_owned_material(material_id, user.id)
        files = await self.files.list_by_material(material.id)
        if not any(item.id == file_id for item in files):
            raise ResourceNotFound("Material file not found")
        if cover is None and primary is None:
            raise ValidationAppError("At least one of cover or primary must be provided")
        self._ensure_material_is_editable(material)
        await self._mark_material_for_rereview_if_needed(material, user.id)

        if cover is True:
            material.cover_file_id = file_id
        elif cover is False and material.cover_file_id == file_id:
            material.cover_file_id = None

        if primary is True:
            material.primary_file_id = file_id
        elif primary is False and material.primary_file_id == file_id:
            material.primary_file_id = None

        await self.session.commit()
        await self._invalidate_material_caches()
        return await self.materials.get(material.id)

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

    async def prepare_download(
        self,
        identifier: str,
        file_id: str | None,
        user: User | None = None,
        lookup_field: str = "id",
    ) -> StorageDownload:
        material = await self.get_material_for_view(identifier, user, lookup_field)
        if material.status == MaterialStatus.APPROVED and user is None:
            raise AuthenticationError("Authentication is required to download this material")
        file_entry = (
            await self.files.get(file_id)
            if file_id
            else await self.files.get(material.primary_file_id or material.cover_file_id or material.files[0].id)
        )
        if not file_entry or file_entry.material_id != material.id:
            raise ResourceNotFound("Material file not found")
        if not await self.storage.exists(file_entry.storage_key):
            raise ResourceNotFound("Stored file not found")

        should_increment = True
        if user is not None:
            existing_download = await self.session.scalar(
                select(MaterialDownload).where(
                    MaterialDownload.user_id == user.id,
                    MaterialDownload.material_id == material.id
                ).limit(1)
            )
            if existing_download:
                should_increment = False
            else:
                download_record = MaterialDownload(
                    user_id=user.id,
                    material_id=material.id,
                )
                self.session.add(download_record)

        if should_increment:
            await self.session.execute(
                update(Material)
                .where(Material.id == material.id)
                .values(download_count=Material.download_count + 1)
            )

        await self.session.commit()
        await self.cache.invalidate("materials:stats_summary")
        await self.cache.invalidate("materials:trending_ids")
        return await self.storage.resolve_for_download(file_entry.storage_key, filename=file_entry.original_filename)

    async def prepare_preview(
        self,
        identifier: str,
        file_id: str,
        user: User | None = None,
        lookup_field: str = "id",
    ) -> tuple[StorageDownload, str]:
        material = await self.get_material_for_view(identifier, user, lookup_field)
        file_entry = await self.files.get(file_id)
        if not file_entry or file_entry.material_id != material.id:
            raise ResourceNotFound("Material file not found")
        if not file_entry.is_previewable:
            raise PermissionDenied("File is not previewable")
        LARGE_FILE_LIMIT_BYTES = 20 * 1024 * 1024
        is_large_pdf = file_entry.file_ext == "pdf" and file_entry.file_size > LARGE_FILE_LIMIT_BYTES

        if (material.status == MaterialStatus.APPROVED and user is None) or is_large_pdf:
            if file_entry.file_kind == FileKind.IMAGE:
                return await self.storage.resolve_for_download(file_entry.storage_key, filename=file_entry.original_filename, disposition="inline"), "full"
            if file_entry.file_ext == "pdf":
                if not file_entry.preview_storage_key:
                    preview_storage_key, preview_page_count = await self._build_pdf_preview(
                        material.id,
                        file_entry.storage_key,
                    )
                    file_entry.preview_storage_key = preview_storage_key
                    file_entry.preview_page_count = preview_page_count
                    await self.session.commit()
                return await self.storage.resolve_for_download(file_entry.preview_storage_key, filename=f"preview_{file_entry.original_filename}", disposition="inline"), "limited"
            raise AuthenticationError("Authentication is required to preview this file")
        return await self.storage.resolve_for_download(file_entry.storage_key, filename=file_entry.original_filename, disposition="inline"), "full"

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

    @staticmethod
    def _ensure_material_is_editable(material: Material) -> None:
        if material.status == MaterialStatus.PENDING_REVIEW:
            raise ConflictError("Pending review material must be withdrawn before editing")

    async def _mark_material_for_rereview_if_needed(self, material: Material, actor_id: str) -> None:
        if material.status != MaterialStatus.APPROVED:
            return
        material.status = MaterialStatus.PENDING_REVIEW
        material.submitted_at = datetime.now(UTC)
        await self.logs.create(
            MaterialReviewLog(material_id=material.id, action=ReviewAction.RESUBMITTED, actor_id=actor_id)
        )

    async def _ensure_subject(self, subject_id: str) -> None:
        if not await self.subjects.get(subject_id):
            raise ResourceNotFound("Subject not found")

    async def _get_material(self, identifier: str, lookup_field: str) -> Material | None:
        if lookup_field == "slug":
            return await self.materials.get_by_slug(identifier)
        return await self.materials.get(identifier)

    async def _generate_unique_slug(self, title: str) -> str:
        base_slug = slugify(title)
        slug = base_slug
        suffix = 2
        while await self.materials.get_by_slug(slug):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        return slug

    async def get_material_access_context(self, material: Material, user: User | None) -> dict[str, object]:
        if material.status != MaterialStatus.APPROVED:
            if user and user.role.value in {"admin", "moderator"}:
                return self._build_access_context("moderator", True, True, False)
            if user and material.uploaded_by == user.id:
                return self._build_access_context("owner", True, True, False)
            return self._build_access_context("restricted", False, False, True)

        previewable_files = [file for file in material.files if file.is_previewable]
        if user is None:
            can_preview = any(
                file.file_kind == FileKind.IMAGE or (file.file_ext == "pdf")
                for file in previewable_files
            )
            preview_page_limit = PDF_PREVIEW_PAGE_LIMIT if any(file.file_ext == "pdf" for file in previewable_files) else None
            return self._build_access_context("public", False, can_preview, True, preview_page_limit)

        return self._build_access_context("authenticated", True, bool(previewable_files), False)

    async def list_sitemap_entries(self) -> list[dict[str, str]]:
        items = await self.materials.list_approved_for_sitemap()
        base_url = self.settings.public_web_base_url.rstrip("/")
        return [
            {
                "loc": f"{base_url}/materials/{item.slug}",
                "lastmod": item.updated_at.date().isoformat(),
            }
            for item in items
        ]

    async def _build_pdf_preview(self, material_id: str, storage_key: str) -> tuple[str, int]:
        source_bytes = await self.storage.read_bytes(storage_key)
        reader = PdfReader(io.BytesIO(source_bytes))
        page_count = min(len(reader.pages), PDF_PREVIEW_PAGE_LIMIT)
        writer = PdfWriter()
        for index in range(page_count):
            writer.add_page(reader.pages[index])

        buffer = io.BytesIO()
        writer.write(buffer)
        preview_storage_key = f"materials/{material_id}/previews/{uuid4()}.pdf"
        await self.storage.save_bytes(buffer.getvalue(), preview_storage_key, "application/pdf")
        return preview_storage_key, page_count

    @staticmethod
    def _build_access_context(
        access_level: str,
        can_download: bool,
        can_preview: bool,
        requires_auth_for_download: bool,
        preview_page_limit: int | None = None,
    ) -> dict[str, object]:
        return {
            "access_level": access_level,
            "can_download": can_download,
            "can_preview": can_preview,
            "requires_auth_for_download": requires_auth_for_download,
            "preview_page_limit": preview_page_limit,
        }

    async def _invalidate_material_caches(self) -> None:
        await self.cache.invalidate("materials:stats_summary")
        await self.cache.invalidate("materials:trending_ids")
        await self.cache.invalidate_prefix("admin:dashboard_")

    async def _best_effort_delete_storage_keys(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            try:
                await self.storage.delete(key)
            except Exception:
                continue
