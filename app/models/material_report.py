from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums.report_status import ReportStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


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
