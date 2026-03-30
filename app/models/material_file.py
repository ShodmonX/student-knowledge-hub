from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums.file_kind import FileKind
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


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
    is_previewable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preview_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    material = relationship("Material", back_populates="files", foreign_keys=[material_id])
