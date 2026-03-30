from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Faculty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "faculties"
    __table_args__ = (UniqueConstraint("university_id", "slug", name="uq_faculty_university_slug"),)

    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    university = relationship("University", back_populates="faculties")
    subjects = relationship("Subject", back_populates="faculty", cascade="all, delete-orphan")
