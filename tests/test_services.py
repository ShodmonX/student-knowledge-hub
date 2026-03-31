from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConflictError, PermissionDenied, ResourceNotFound, ValidationAppError
from app.modules.materials.enums import MaterialStatus, ReportStatus
from app.modules.users.enums import UserRole
from app.modules.admin.repository import ModeratorScopeRepository
from app.modules.moderation.schemas import MoveSubjectRequest, RejectRequest
from app.modules.tags.schemas import TagCreate, TagUpdate
from app.modules.admin.service import AdminService
from app.modules.community.service import CommunityService
from app.modules.moderation.service import ModerationService
from app.modules.tags.service import TagService
from tests.helpers import add_university_scope, seed_faculty, seed_material, seed_report, seed_subject, seed_university, seed_user


@pytest.mark.asyncio
async def test_admin_service_direct_covers_validation_reports_and_dashboard(session):
    university = await seed_university(session, "Admin Service University")
    second_university = await seed_university(session, "Admin Service University 2")
    faculty = await seed_faculty(session, university.id, "Admin Faculty")
    subject = await seed_subject(session, faculty.id, "Admin Subject", 1)

    managed_user = await seed_user(session, university.id, "managed-service@example.com")
    report_user = await seed_user(session, university.id, "report-service@example.com")
    uploader = await seed_user(session, university.id, "uploader-service@example.com")
    service = AdminService(session)

    updated_role_user = await service.update_user_role(managed_user.id, UserRole.MODERATOR)
    assert updated_role_user.role == UserRole.MODERATOR

    updated_user = await service.update_user(managed_user.id, {"full_name": "Managed Service User"})
    assert updated_user.full_name == "Managed Service User"
    assert (await service.set_user_status(managed_user.id, False)).is_active is False
    assert (await service.verify_user(managed_user.id, True)).is_verified is True

    filtered_users, total = await service.list_users(q="managed", role="moderator", status=False, university_id=university.id)
    assert total == 1
    assert filtered_users[0].id == managed_user.id
    assert (await service.get_user_detail(managed_user.id)).id == managed_user.id

    with pytest.raises(ResourceNotFound):
        await service.get_user_detail("missing-user")
    with pytest.raises(ValidationAppError):
        await service.add_moderator_scope(managed_user.id, type("Payload", (), {"university_id": None, "faculty_id": None, "subject_id": None})())
    with pytest.raises(ValidationAppError):
        await service.add_moderator_scope(
            managed_user.id,
            type("Payload", (), {"university_id": university.id, "faculty_id": faculty.id, "subject_id": None})(),
        )

    result = await service.add_moderator_scope(
        managed_user.id,
        type("Payload", (), {"university_id": second_university.id, "faculty_id": None, "subject_id": None})(),
    )
    assert result["message"] == "Moderator scope assigned"
    scope_id = result["scope_id"]

    listed_scopes = await service.list_moderator_scopes(managed_user.id)
    assert len(listed_scopes) == 1
    assert listed_scopes[0]["scope_id"] == second_university.id
    all_scopes = await service.list_all_moderator_scopes()
    assert any(item["scope_id"] == second_university.id for item in all_scopes)

    scope_ids = await ModeratorScopeRepository(session).list_scope_ids(managed_user.id)
    assert second_university.id in scope_ids["universities"]

    with pytest.raises(ResourceNotFound):
        await service.delete_moderator_scope(managed_user.id, "missing-scope")
    await service.delete_moderator_scope(managed_user.id, scope_id)

    material = await seed_material(session, uploader, subject.id, "Admin Service Material", status=MaterialStatus.APPROVED)
    material.download_count = 4
    material.reviewed_at = datetime.now(UTC)
    session.add(material)
    await session.commit()

    open_report = await seed_report(session, material.id, report_user.id, reason="spam")
    dismissed_report = await seed_report(session, material.id, report_user.id, reason="copyright")

    reports, total_reports = await service.list_reports(status=ReportStatus.OPEN)
    assert total_reports == 2
    assert len(reports) == 2
    assert (await service.get_report(open_report.id)).id == open_report.id

    with pytest.raises(ResourceNotFound):
        await service.get_report("missing-report")

    updated_report = await service.update_report(open_report.id, {"resolution_note": "triaged"})
    assert updated_report.resolution_note == "triaged"

    resolved_report = await service.resolve_report(open_report.id, "resolved note")
    assert resolved_report.status == ReportStatus.RESOLVED
    dismissed = await service.dismiss_report(dismissed_report.id, "dismissed note")
    assert dismissed.status == ReportStatus.DISMISSED

    audit_logs, audit_total = await service.list_audit_logs(entity="material_report")
    assert audit_total >= 1
    assert len(audit_logs) >= 1

    summary = await service.dashboard_summary()
    charts = await service.dashboard_charts()
    assert summary["total_materials"] >= 1
    assert "top_universities" in charts
    assert "top_material_types" in charts


@pytest.mark.asyncio
async def test_moderation_service_direct_covers_scope_and_state_conflicts(session):
    university = await seed_university(session, "Moderation University")
    faculty = await seed_faculty(session, university.id, "Moderation Faculty")
    subject = await seed_subject(session, faculty.id, "Moderation Subject", 1)
    other_subject = await seed_subject(session, faculty.id, "Moderation Other Subject", 2)
    foreign_university = await seed_university(session, "Foreign Moderation University")
    foreign_faculty = await seed_faculty(session, foreign_university.id, "Foreign Faculty")
    foreign_subject = await seed_subject(session, foreign_faculty.id, "Foreign Subject", 1)

    admin = await seed_user(session, university.id, "moderation-admin@example.com", role=UserRole.ADMIN)
    moderator = await seed_user(session, university.id, "moderation-mod@example.com", role=UserRole.MODERATOR)
    no_scope_moderator = await seed_user(session, university.id, "moderation-none@example.com", role=UserRole.MODERATOR)
    owner = await seed_user(session, university.id, "moderation-owner@example.com")
    foreign_owner = await seed_user(session, foreign_university.id, "moderation-foreign@example.com")
    await add_university_scope(session, moderator.id, university.id)

    approvable = await seed_material(session, owner, subject.id, "Approvable", status=MaterialStatus.PENDING_REVIEW)
    approvable.file_count = 1
    pending_reject = await seed_material(session, owner, subject.id, "Rejectable", status=MaterialStatus.PENDING_REVIEW)
    pending_request_revision = await seed_material(
        session,
        owner,
        subject.id,
        "Revision Needed",
        status=MaterialStatus.PENDING_REVIEW,
    )
    no_file_pending = await seed_material(session, owner, subject.id, "No File Pending", status=MaterialStatus.PENDING_REVIEW)
    foreign_pending = await seed_material(
        session,
        foreign_owner,
        foreign_subject.id,
        "Foreign Pending",
        status=MaterialStatus.PENDING_REVIEW,
    )
    session.add(approvable)
    await session.commit()

    service = ModerationService(session)
    pending_items = await service.list_pending(moderator)
    assert {item.id for item in pending_items} >= {approvable.id, pending_reject.id, pending_request_revision.id, no_file_pending.id}
    assert foreign_pending.id not in {item.id for item in pending_items}
    assert await service.list_pending(no_scope_moderator) == []
    admin_pending = await service.list_pending(admin)
    assert foreign_pending.id in {item.id for item in admin_pending}

    approved_material = await service.approve(approvable.id, moderator)
    assert approved_material.status == MaterialStatus.APPROVED

    with pytest.raises(ConflictError):
        await service.approve(no_file_pending.id, moderator)
    with pytest.raises(ConflictError):
        await service.reject(approved_material.id, RejectRequest(reason="spam", note=None), moderator)
    with pytest.raises(PermissionDenied):
        await service.reject(foreign_pending.id, RejectRequest(reason="spam", note=None), moderator)
    with pytest.raises(ResourceNotFound):
        await service.move_subject(approved_material.id, MoveSubjectRequest(subject_id="missing", note=None), moderator)

    rejected_material = await service.reject(
        pending_reject.id,
        RejectRequest(reason="duplicate", note="duplicate"),
        moderator,
    )
    assert rejected_material.status == MaterialStatus.REJECTED
    revised_material = await service.request_revision(
        pending_request_revision.id,
        RejectRequest(reason="low_quality", note="revise"),
        moderator,
    )
    assert revised_material.status == MaterialStatus.REJECTED
    moved_material = await service.move_subject(approved_material.id, MoveSubjectRequest(subject_id=other_subject.id, note="move"), admin)
    assert moved_material.subject_id == other_subject.id

    history = await service.history(rejected_material.id, moderator)
    context = await service.context(rejected_material.id, moderator)
    assert history[0].material_id == rejected_material.id
    assert context["material_id"] == rejected_material.id


@pytest.mark.asyncio
async def test_tag_service_direct_covers_conflicts_validation_and_delete(session):
    service = TagService(session)
    assert await service.list_tags() == []

    tag = await service.create_tag(TagCreate(name="  Math  "))
    assert tag.name == "Math"
    assert tag.slug == "math"
    assert (await service.get_tag(tag.id)).id == tag.id

    with pytest.raises(ConflictError):
        await service.create_tag(TagCreate(name="math"))
    with pytest.raises(ResourceNotFound):
        await service.get_tag("missing-tag")
    with pytest.raises(ValidationAppError):
        await service.update_tag(tag.id, TagUpdate(name="   "))
    fallback_slug = await service.update_tag(tag.id, TagUpdate(slug="   "))
    assert fallback_slug.slug == "item"

    updated = await service.update_tag(tag.id, TagUpdate(name="Physics"))
    assert updated.name == "Physics"
    assert updated.slug == "physics"

    other_tag = await service.create_tag(TagCreate(name="Chemistry"))
    with pytest.raises(ConflictError):
        await service.update_tag(other_tag.id, TagUpdate(name="Physics"))

    await service.delete_tag(other_tag.id)
    with pytest.raises(ResourceNotFound):
        await service.get_tag(other_tag.id)


@pytest.mark.asyncio
async def test_community_service_direct_covers_negative_paths_and_ratings(session):
    university = await seed_university(session, "Community Direct University")
    faculty = await seed_faculty(session, university.id, "Community Direct Faculty")
    subject = await seed_subject(session, faculty.id, "Community Direct Subject", 1)
    owner = await seed_user(session, university.id, "community-direct-owner@example.com")
    other_user = await seed_user(session, university.id, "community-direct-other@example.com")
    admin = await seed_user(session, university.id, "community-direct-admin@example.com", role=UserRole.ADMIN)
    material = await seed_material(session, owner, subject.id, "Community Direct Material", status=MaterialStatus.APPROVED)
    service = CommunityService(session)

    assert await service.list_comments(material.id) == []
    with pytest.raises(ResourceNotFound):
        await service.create_comment("missing-material", type("Payload", (), {"content": "x"})(), owner)

    comment = await service.create_comment(material.id, type("Payload", (), {"content": "hello"})(), owner)
    assert comment.content == "hello"

    with pytest.raises(ResourceNotFound):
        await service.update_comment("missing-comment", type("Payload", (), {"content": "new"})(), owner)
    with pytest.raises(PermissionDenied):
        await service.update_comment(comment.id, type("Payload", (), {"content": "new"})(), other_user)

    updated_comment = await service.update_comment(comment.id, type("Payload", (), {"content": "updated"})(), owner)
    assert updated_comment.content == "updated"

    with pytest.raises(PermissionDenied):
        await service.delete_comment(comment.id, other_user)
    await service.delete_comment(comment.id, admin)

    with pytest.raises(ResourceNotFound):
        await service.get_rating_summary("missing-material", owner)

    created_rating = await service.rate(material.id, 5, owner)
    updated_rating = await service.rate(material.id, 3, owner)
    assert created_rating["average"] == 5.0
    assert updated_rating["average"] == 3.0
    assert updated_rating["my_rating"] == 3

    await service.unrate(material.id, owner)
    with pytest.raises(ConflictError):
        await service.unrate(material.id, owner)
