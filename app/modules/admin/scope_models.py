from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ModeratorUniversityScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "moderator_university_scopes"
    __table_args__ = (UniqueConstraint("user_id", "university_id", name="uq_mod_uni_scope"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)


class ModeratorFacultyScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "moderator_faculty_scopes"
    __table_args__ = (UniqueConstraint("user_id", "faculty_id", name="uq_mod_fac_scope"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    faculty_id: Mapped[str] = mapped_column(ForeignKey("faculties.id", ondelete="CASCADE"), nullable=False, index=True)


class ModeratorSubjectScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "moderator_subject_scopes"
    __table_args__ = (UniqueConstraint("user_id", "subject_id", name="uq_mod_sub_scope"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
