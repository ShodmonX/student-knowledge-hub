from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.materials.enums import MaterialStatus
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.materials.models import Material, MaterialFile, MaterialReviewLog
from app.modules.community.models import MaterialRating
from app.modules.tags.models import Tag
from app.modules.users.models import User


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, material_id: str) -> Material | None:
        result = await self.session.execute(
            select(Material)
            .where(Material.id == material_id)
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Material | None:
        result = await self.session.execute(
            select(Material)
            .where(Material.slug == slug)
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
        )
        return result.scalar_one_or_none()

    async def get_many(self, material_ids: list[str]) -> list[Material]:
        if not material_ids:
            return []
        result = await self.session.execute(
            select(Material)
            .where(Material.id.in_(material_ids), Material.deleted_at.is_(None))
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
        )
        items = {item.id: item for item in result.scalars().all()}
        return [items[item_id] for item_id in material_ids if item_id in items]

    async def create(self, material: Material) -> Material:
        self.session.add(material)
        await self.session.flush()
        await self.session.refresh(material)
        return material

    async def list_for_owner(self, owner_id: str) -> list[Material]:
        result = await self.session.execute(
            select(Material)
            .where(Material.uploaded_by == owner_id, Material.deleted_at.is_(None))
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
            .order_by(Material.created_at.desc())
        )
        return list(result.scalars().all())

    def build_filtered_query(self) -> Select[tuple[Material]]:
        return (
            select(Material)
            .join(Subject, Subject.id == Material.subject_id)
            .join(Faculty, Faculty.id == Subject.faculty_id)
            .join(University, University.id == Faculty.university_id)
            .options(
                selectinload(Material.files),
                selectinload(Material.tags),
                selectinload(Material.subject).selectinload(Subject.faculty).selectinload(Faculty.university),
                selectinload(Material.uploader).selectinload(User.university),
            )
            .where(Material.deleted_at.is_(None))
        )

    async def list_filtered(self, statement: Select[tuple[Material]], page: int, page_size: int):
        count_stmt = select(func.count()).select_from(statement.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        result = await self.session.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_file_for_download(self, material_id: str, file_id: str) -> MaterialFile | None:
        result = await self.session.execute(
            select(MaterialFile).where(MaterialFile.material_id == material_id, MaterialFile.id == file_id)
        )
        return result.scalar_one_or_none()

    async def list_approved_for_sitemap(self) -> list[Material]:
        result = await self.session.execute(
            select(Material)
            .where(
                Material.deleted_at.is_(None),
                Material.status == MaterialStatus.APPROVED,
            )
            .order_by(Material.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def apply_filters(statement: Select[tuple[Material]], query, include_text: bool = True):
        if include_text and query.q:
            search_text = query.q.strip()
            if search_text:
                search_pattern = f"%{escape_like(search_text)}%"
                statement = statement.where(
                    or_(
                        Material.title.ilike(search_pattern, escape="\\"),
                        Material.description.ilike(search_pattern, escape="\\"),
                        Subject.name.ilike(search_pattern, escape="\\"),
                        Faculty.name.ilike(search_pattern, escape="\\"),
                        University.name.ilike(search_pattern, escape="\\"),
                        Material.tags.any(Tag.name.ilike(search_pattern, escape="\\")),
                        Material.tags.any(Tag.slug.ilike(search_pattern, escape="\\")),
                    )
                )
        if query.subject_id:
            statement = statement.where(Material.subject_id == query.subject_id)
        if query.faculty_id:
            statement = statement.where(Subject.faculty_id == query.faculty_id)
        if query.university_id:
            statement = statement.where(Faculty.university_id == query.university_id)
        if query.material_type:
            statement = statement.where(Material.material_type == query.material_type)
        if query.semester:
            statement = statement.where(Subject.semester == query.semester)
        if getattr(query, "course", None):
            statement = statement.where(Subject.semester == query.course)
        if query.status:
            statement = statement.where(Material.status == query.status)
        if getattr(query, "only_approved", None):
            statement = statement.where(Material.status == MaterialStatus.APPROVED)
        if getattr(query, "is_public", None):
            statement = statement.where(Material.status == MaterialStatus.APPROVED)
        if getattr(query, "uploaded_by", None):
            statement = statement.where(Material.uploaded_by == query.uploaded_by)
        if getattr(query, "download_count_gte", None) is not None:
            statement = statement.where(Material.download_count >= query.download_count_gte)
        if getattr(query, "file_format", None):
            statement = statement.where(Material.files.any(MaterialFile.file_ext == query.file_format.lower()))

        if query.sort == "rating_desc":
            rating_summary = (
                select(
                    MaterialRating.material_id.label("material_id"),
                    func.avg(MaterialRating.value).label("average_rating"),
                    func.count(MaterialRating.id).label("rating_count"),
                )
                .group_by(MaterialRating.material_id)
                .subquery()
            )
            return (
                statement.outerjoin(rating_summary, rating_summary.c.material_id == Material.id)
                .order_by(
                    func.coalesce(rating_summary.c.average_rating, 0).desc(),
                    func.coalesce(rating_summary.c.rating_count, 0).desc(),
                    Material.created_at.desc(),
                )
            )

        order_map = {
            "created_at_desc": Material.created_at.desc(),
            "created_at_asc": Material.created_at.asc(),
            "title_asc": Material.title.asc(),
            "download_count_desc": Material.download_count.desc(),
        }
        return statement.order_by(order_map.get(query.sort, Material.created_at.desc()))


class MaterialFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(self, files: list[MaterialFile]) -> list[MaterialFile]:
        self.session.add_all(files)
        await self.session.flush()
        return files

    async def get(self, file_id: str) -> MaterialFile | None:
        return await self.session.get(MaterialFile, file_id)

    async def list_by_material(self, material_id: str) -> list[MaterialFile]:
        result = await self.session.execute(
            select(MaterialFile)
            .where(MaterialFile.material_id == material_id)
            .order_by(MaterialFile.file_order.asc())
        )
        return list(result.scalars().all())


class MaterialReviewLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, log: MaterialReviewLog) -> MaterialReviewLog:
        self.session.add(log)
        await self.session.flush()
        return log
