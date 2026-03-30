from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums.material_status import MaterialStatus
from app.enums.material_type import MaterialType
from app.enums.reject_reason import RejectReason
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Material(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "materials"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_type: Mapped[MaterialType] = mapped_column(Enum(MaterialType), nullable=False)
    status: Mapped[MaterialStatus] = mapped_column(Enum(MaterialStatus), default=MaterialStatus.DRAFT, index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejected_reason: Mapped[RejectReason | None] = mapped_column(Enum(RejectReason), nullable=True)
    cover_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_files.id", use_alter=True, name="fk_material_cover_file"),
        nullable=True,
    )
    primary_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_files.id", use_alter=True, name="fk_material_primary_file"),
        nullable=True,
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subject = relationship("Subject", back_populates="materials")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="uploaded_materials")
    files = relationship(
        "MaterialFile",
        back_populates="material",
        foreign_keys="MaterialFile.material_id",
        primaryjoin="and_(Material.id==MaterialFile.material_id)",
        order_by="MaterialFile.file_order",
        cascade="all, delete-orphan",
    )
    review_logs = relationship("MaterialReviewLog", back_populates="material", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="material_tags", back_populates="materials")

    def mark_deleted(self) -> None:
        self.deleted_at = datetime.now(UTC)
