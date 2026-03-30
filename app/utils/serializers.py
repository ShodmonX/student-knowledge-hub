from __future__ import annotations

from app.models.audit_log import AuditLog
from app.models.catalog_proposal import FacultyProposal, SubjectProposal, UniversityProposal
from app.models.comment import Comment
from app.models.material import Material
from app.models.material_report import MaterialReport
from app.models.university import University
from app.models.user import User
from app.schemas.audit import AuditLogRead
from app.schemas.catalog_proposal import CatalogProposalRead
from app.schemas.comment import CommentRead
from app.schemas.material import MaterialRead
from app.schemas.report import MaterialReportRead
from app.schemas.summary import (
    FacultySummary,
    MaterialSummary,
    PublicUserSummary,
    SubjectSummary,
    UniversitySummary,
)


def build_university_summary(university: University | None) -> UniversitySummary | None:
    if not university:
        return None
    return UniversitySummary(id=university.id, name=university.name, slug=university.slug)


def build_public_user_summary(user: User | None) -> PublicUserSummary | None:
    if not user:
        return None
    return PublicUserSummary(
        id=user.id,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        university=build_university_summary(getattr(user, "university", None)),
    )


def build_material_read(material: Material, average_rating: float = 0.0, rating_count: int = 0) -> MaterialRead:
    subject = getattr(material, "subject", None)
    faculty = getattr(subject, "faculty", None) if subject else None
    university = getattr(faculty, "university", None) if faculty else None
    subject_summary = (
        SubjectSummary(
            id=subject.id,
            name=subject.name,
            slug=subject.slug,
            semester=subject.semester,
            faculty_id=subject.faculty_id,
        )
        if subject
        else None
    )
    faculty_summary = (
        FacultySummary(
            id=faculty.id,
            name=faculty.name,
            slug=faculty.slug,
            university_id=faculty.university_id,
        )
        if faculty
        else None
    )
    return MaterialRead(
        id=material.id,
        title=material.title,
        description=material.description,
        material_type=material.material_type,
        status=material.status,
        subject_id=material.subject_id,
        uploaded_by=material.uploaded_by,
        approved_by=material.approved_by,
        last_reviewed_by=material.last_reviewed_by,
        rejected_reason=material.rejected_reason,
        cover_file_id=material.cover_file_id,
        primary_file_id=material.primary_file_id,
        file_count=material.file_count,
        total_size=material.total_size,
        download_count=material.download_count,
        submitted_at=material.submitted_at,
        reviewed_at=material.reviewed_at,
        created_at=material.created_at,
        updated_at=material.updated_at,
        files=[file for file in material.files],
        uploader=build_public_user_summary(getattr(material, "uploader", None)),
        subject=subject_summary,
        faculty=faculty_summary,
        university=build_university_summary(university),
        average_rating=average_rating,
        rating_count=rating_count,
    )


def build_material_summary(material: Material) -> MaterialSummary:
    return MaterialSummary(
        id=material.id,
        title=material.title,
        material_type=material.material_type.value,
        download_count=material.download_count,
        created_at=material.created_at,
    )


def build_comment_read(comment: Comment, user: User | None = None) -> CommentRead:
    owner = user or getattr(comment, "user", None)
    return CommentRead(
        id=comment.id,
        material_id=comment.material_id,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        user=build_public_user_summary(owner),
    )


def build_report_read(report: MaterialReport) -> MaterialReportRead:
    return MaterialReportRead(
        id=report.id,
        reason=report.reason,
        details=report.details,
        status=report.status,
        resolution_note=report.resolution_note,
        reviewed_at=report.reviewed_at,
        created_at=report.created_at,
        reporter=build_public_user_summary(getattr(report, "reporter", None)),
        material=build_material_summary(report.material),
    )


def build_audit_log_read(log: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=log.id,
        entity=log.entity,
        entity_id=log.entity_id,
        action=log.action,
        details=log.details,
        created_at=log.created_at,
        actor=build_public_user_summary(getattr(log, "actor", None)),
    )


def build_catalog_proposal_read(
    proposal: UniversityProposal | FacultyProposal | SubjectProposal,
    proposal_type: str,
    creator: User | None = None,
) -> CatalogProposalRead:
    proposal_creator = creator
    if proposal_creator is None and "creator" in proposal.__dict__:
        proposal_creator = proposal.__dict__["creator"]
    return CatalogProposalRead(
        id=proposal.id,
        proposal_type=proposal_type,
        status=proposal.status,
        proposed_name=proposal.proposed_name,
        proposed_description=getattr(proposal, "proposed_description", None),
        parent_id=getattr(proposal, "university_id", None) or getattr(proposal, "faculty_id", None),
        proposed_code=getattr(proposal, "proposed_code", None),
        proposed_semester=getattr(proposal, "proposed_semester", None),
        created_at=proposal.created_at,
        reviewed_at=proposal.reviewed_at,
        review_note=proposal.review_note,
        creator=build_public_user_summary(proposal_creator),
    )
