from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFound, ValidationAppError
from app.models.tag import MaterialTag, Tag
from app.schemas.tag import TagCreate, TagUpdate
from app.utils.slug import slugify


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tags(self) -> list[Tag]:
        result = await self.session.execute(select(Tag).order_by(Tag.name.asc()))
        return list(result.scalars().all())

    async def get_tag(self, tag_id: str) -> Tag:
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            raise ResourceNotFound("Tag not found")
        return tag

    async def create_tag(self, payload: TagCreate) -> Tag:
        name = payload.name.strip()
        if not name:
            raise ValidationAppError("Tag name is required")
        slug = slugify(payload.slug) if payload.slug else slugify(name)
        await self._ensure_name_available(name)
        await self._ensure_slug_available(slug)
        tag = Tag(name=name, slug=slug)
        self.session.add(tag)
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def update_tag(self, tag_id: str, payload: TagUpdate) -> Tag:
        tag = await self.get_tag(tag_id)
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise ValidationAppError("Tag name is required")
            await self._ensure_name_available(name, exclude_id=tag.id)
            tag.name = name
        if payload.slug is not None:
            slug = slugify(payload.slug)
            if not slug:
                raise ValidationAppError("Tag slug is required")
            await self._ensure_slug_available(slug, exclude_id=tag.id)
            tag.slug = slug
        elif payload.name is not None:
            slug = slugify(tag.name)
            await self._ensure_slug_available(slug, exclude_id=tag.id)
            tag.slug = slug
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def delete_tag(self, tag_id: str) -> None:
        tag = await self.get_tag(tag_id)
        await self.session.execute(delete(MaterialTag).where(MaterialTag.c.tag_id == tag.id))
        await self.session.delete(tag)
        await self.session.commit()

    async def _ensure_name_available(self, name: str, exclude_id: str | None = None) -> None:
        statement = select(Tag.id).where(func.lower(func.trim(Tag.name)) == name.strip().lower())
        if exclude_id:
            statement = statement.where(Tag.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Tag with this name already exists")

    async def _ensure_slug_available(self, slug: str, exclude_id: str | None = None) -> None:
        statement = select(Tag.id).where(Tag.slug == slug)
        if exclude_id:
            statement = statement.where(Tag.id != exclude_id)
        result = await self.session.execute(statement)
        if result.scalar_one_or_none():
            raise ConflictError("Tag with this slug already exists")
