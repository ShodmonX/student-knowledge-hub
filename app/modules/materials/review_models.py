from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.materials.enums import ReportStatus, ReviewAction
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MaterialReviewLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_review_logs"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    action: Mapped[ReviewAction] = mapped_column(Enum(ReviewAction), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    material = relationship("Material", back_populates="review_logs")


class MaterialReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_reports"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.OPEN, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    material = relationship("Material")
    reporter = relationship("User", foreign_keys=[reporter_id])
