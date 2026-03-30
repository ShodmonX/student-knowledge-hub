from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums.review_action import ReviewAction
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MaterialReviewLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_review_logs"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    action: Mapped[ReviewAction] = mapped_column(Enum(ReviewAction), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    material = relationship("Material", back_populates="review_logs")
