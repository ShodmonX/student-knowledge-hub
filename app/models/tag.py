from __future__ import annotations

from sqlalchemy import ForeignKey, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

material_tags = Table(
    "material_tags",
    Base.metadata,
    Column("material_id", ForeignKey("materials.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Tag(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    materials = relationship("Material", secondary=material_tags, back_populates="tags")


MaterialTag = material_tags
