from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    user = relationship("User")
    material = relationship("Material")


class MaterialRating(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_ratings"
    __table_args__ = (UniqueConstraint("user_id", "material_id", name="uq_material_rating_user_material"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
