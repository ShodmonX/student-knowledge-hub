from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.users.enums import UserRole
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)
    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id"), nullable=False, index=True)
    university_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    university = relationship("University", back_populates="users")
    uploaded_materials = relationship("Material", back_populates="uploader", foreign_keys="Material.uploaded_by")


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(16), default="uz", nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    marketing_notifications: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    theme: Mapped[str] = mapped_column(String(32), default="system", nullable=False)


class SavedMaterial(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_materials"
    __table_args__ = (UniqueConstraint("user_id", "material_id", name="uq_saved_material_user_material"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
