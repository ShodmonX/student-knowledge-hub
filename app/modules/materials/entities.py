from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.materials.enums import FileKind, MaterialStatus, MaterialType, RejectReason
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Material(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "materials"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
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


class MaterialFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_files"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    preview_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_ext: Mapped[str] = mapped_column(String(32), nullable=False)
    file_kind: Mapped[FileKind] = mapped_column(Enum(FileKind), nullable=False, index=True)
    file_order: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_previewable: Mapped[bool] = mapped_column(default=False, nullable=False)
    preview_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    material = relationship("Material", back_populates="files", foreign_keys=[material_id])


class MaterialDownload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_downloads"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "material_id", name="uq_user_material_download"),
    )

    material = relationship("Material", foreign_keys=[material_id])
    user = relationship("User", foreign_keys=[user_id])
