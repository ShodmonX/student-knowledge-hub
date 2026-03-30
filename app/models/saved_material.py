from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SavedMaterial(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_materials"
    __table_args__ = (UniqueConstraint("user_id", "material_id", name="uq_saved_material_user_material"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
