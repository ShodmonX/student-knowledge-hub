from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.catalog_proposals.enums import ProposalEntityType, ProposalStatus
from app.modules.materials.enums import ReportStatus
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class UniversityProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "university_proposals"

    proposed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_university_id: Mapped[str | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])


class FacultyProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "faculty_proposals"

    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    proposed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_faculty_id: Mapped[str | None] = mapped_column(ForeignKey("faculties.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])


class SubjectProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subject_proposals"

    faculty_id: Mapped[str] = mapped_column(ForeignKey("faculties.id", ondelete="CASCADE"), nullable=False, index=True)
    proposed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_subject_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])


class CatalogProposalLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_proposal_logs"

    entity_type: Mapped[ProposalEntityType] = mapped_column(Enum(ProposalEntityType), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CatalogReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_reports"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "university", "faculty", "subject"
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(String(32), default=ReportStatus.OPEN, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reporter = relationship("User", foreign_keys=[reporter_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])

