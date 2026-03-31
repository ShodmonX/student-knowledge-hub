from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class University(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "universities"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    faculties = relationship("Faculty", back_populates="university", cascade="all, delete-orphan")
    users = relationship("User", back_populates="university")


class Faculty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "faculties"
    __table_args__ = (UniqueConstraint("university_id", "slug", name="uq_faculty_university_slug"),)

    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    university = relationship("University", back_populates="faculties")
    subjects = relationship("Subject", back_populates="faculty", cascade="all, delete-orphan")


class Subject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("faculty_id", "slug", "semester", name="uq_subject_faculty_slug_semester"),)

    faculty_id: Mapped[str] = mapped_column(ForeignKey("faculties.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    faculty = relationship("Faculty", back_populates="subjects")
    materials = relationship("Material", back_populates="subject")
