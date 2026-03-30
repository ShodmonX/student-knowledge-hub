import pytest
from sqlalchemy import select

from app.enums.material_status import MaterialStatus
from app.enums.proposal_status import ProposalStatus
from app.enums.report_status import ReportStatus
from app.enums.review_action import ReviewAction
from app.enums.user_role import UserRole
from app.models.audit_log import AuditLog
from app.models.catalog_proposal import FacultyProposal, SubjectProposal, UniversityProposal
from app.models.material_review_log import MaterialReviewLog
from tests.helpers import (
    access_headers,
    add_faculty_scope,
    add_university_scope,
    seed_faculty,
    seed_material,
    seed_report,
    seed_subject,
    seed_university,
    seed_user,
)


@pytest.mark.asyncio
async def test_moderation_material_endpoints_cover_scope_actions_and_context(client, session):
    primary_university = await seed_university(session, "Primary University")
    primary_faculty = await seed_faculty(session, primary_university.id, "Engineering")
    primary_subject = await seed_subject(session, primary_faculty.id, "Algorithms", 3)
    alternate_subject = await seed_subject(session, primary_faculty.id, "Databases", 4)

    secondary_university = await seed_university(session, "Secondary University")
    secondary_faculty = await seed_faculty(session, secondary_university.id, "Medicine")
    foreign_subject = await seed_subject(session, secondary_faculty.id, "Anatomy", 2)

    moderator = await seed_user(
        session,
        primary_university.id,
        "moderator@example.com",
        role=UserRole.MODERATOR,
        full_name="Moderator User",
    )
    await add_faculty_scope(session, moderator.id, primary_faculty.id)

    local_owner = await seed_user(session, primary_university.id, "owner@example.com")
    foreign_owner = await seed_user(session, secondary_university.id, "foreign-owner@example.com")

    approve_target = await seed_material(
        session,
        local_owner,
        primary_subject.id,
        "Approve Me",
        status=MaterialStatus.PENDING_REVIEW,
    )
    reject_target = await seed_material(
        session,
        local_owner,
        primary_subject.id,
        "Reject Me",
        status=MaterialStatus.PENDING_REVIEW,
    )
    revision_target = await seed_material(
        session,
        local_owner,
        primary_subject.id,
        "Revise Me",
        status=MaterialStatus.PENDING_REVIEW,
    )
    move_target = await seed_material(
        session,
        local_owner,
        primary_subject.id,
        "Move Me",
        status=MaterialStatus.PENDING_REVIEW,
    )
    foreign_target = await seed_material(
        session,
        foreign_owner,
        foreign_subject.id,
        "Foreign Pending",
        status=MaterialStatus.PENDING_REVIEW,
    )

    headers = access_headers(moderator)

    pending_response = await client.get("/api/v1/moderation/materials/pending", headers=headers)
    assert pending_response.status_code == 200
    pending_ids = {item["id"] for item in pending_response.json()}
    assert approve_target.id in pending_ids
    assert reject_target.id in pending_ids
    assert revision_target.id in pending_ids
    assert move_target.id in pending_ids
    assert foreign_target.id not in pending_ids

    foreign_reject = await client.patch(
        f"/api/v1/moderation/materials/{foreign_target.id}/reject",
        headers=headers,
        json={"reason": "spam", "note": "out of scope"},
    )
    assert foreign_reject.status_code == 403

    approve_target.file_count = 1
    session.add(approve_target)
    await session.commit()

    approve_response = await client.patch(
        f"/api/v1/moderation/materials/{approve_target.id}/approve",
        headers=headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["last_reviewed_by"] == moderator.id

    reject_response = await client.patch(
        f"/api/v1/moderation/materials/{reject_target.id}/reject",
        headers=headers,
        json={"reason": "duplicate", "note": "Already uploaded"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert reject_response.json()["rejected_reason"] == "duplicate"

    revision_response = await client.post(
        f"/api/v1/moderation/materials/{revision_target.id}/request-revision",
        headers=headers,
        json={"reason": "low_quality", "note": "Please improve scan quality"},
    )
    assert revision_response.status_code == 200
    assert revision_response.json()["status"] == "rejected"
    assert revision_response.json()["rejected_reason"] == "low_quality"

    move_response = await client.patch(
        f"/api/v1/moderation/materials/{move_target.id}/move-subject",
        headers=headers,
        json={"subject_id": alternate_subject.id, "note": "Wrong subject bucket"},
    )
    assert move_response.status_code == 200
    assert move_response.json()["subject_id"] == alternate_subject.id

    history_response = await client.get(
        f"/api/v1/moderation/materials/{reject_target.id}/history",
        headers=headers,
    )
    assert history_response.status_code == 200
    assert history_response.json()[0]["action"] == ReviewAction.REJECTED.value

    context_response = await client.get(
        f"/api/v1/moderation/materials/{move_target.id}/context",
        headers=headers,
    )
    assert context_response.status_code == 200
    assert context_response.json()["material_id"] == move_target.id
    assert context_response.json()["history"][0]["action"] == ReviewAction.MOVED_SUBJECT.value

    logs = (
        await session.execute(
            select(MaterialReviewLog).where(MaterialReviewLog.material_id == approve_target.id)
        )
    ).scalars().all()
    assert any(log.action == ReviewAction.APPROVED for log in logs)


@pytest.mark.asyncio
async def test_catalog_proposal_moderation_endpoints_cover_review_flows(client, session):
    university = await seed_university(session, "Catalog University")
    faculty = await seed_faculty(session, university.id, "Catalog Faculty")
    existing_subject = await seed_subject(session, faculty.id, "Existing Subject", 1)

    admin = await seed_user(session, university.id, "catalog-admin@example.com", role=UserRole.ADMIN)
    moderator = await seed_user(
        session,
        university.id,
        "catalog-moderator@example.com",
        role=UserRole.MODERATOR,
    )
    student = await seed_user(session, university.id, "catalog-student@example.com")
    await add_university_scope(session, moderator.id, university.id)

    student_headers = access_headers(student)
    admin_headers = access_headers(admin)
    moderator_headers = access_headers(moderator)

    university_create = await client.post(
        "/api/v1/catalog-proposals/universities",
        headers=student_headers,
        json={"name": "Brand New University", "description": "Need a new catalog entry"},
    )
    faculty_create = await client.post(
        "/api/v1/catalog-proposals/faculties",
        headers=student_headers,
        json={"university_id": university.id, "name": "New Faculty", "description": "Missing faculty"},
    )
    subject_reject_create = await client.post(
        "/api/v1/catalog-proposals/subjects",
        headers=student_headers,
        json={"faculty_id": faculty.id, "name": "Distributed Systems", "semester": 5},
    )
    subject_map_create = await client.post(
        "/api/v1/catalog-proposals/subjects",
        headers=student_headers,
        json={"faculty_id": faculty.id, "name": "Existing Subject Copy", "semester": 6},
    )

    assert university_create.status_code == 201
    assert faculty_create.status_code == 201
    assert subject_reject_create.status_code == 201
    assert subject_map_create.status_code == 201

    all_pending = await client.get("/api/v1/moderation/catalog-proposals", headers=admin_headers)
    assert all_pending.status_code == 200
    assert len(all_pending.json()["universities"]) == 1
    assert len(all_pending.json()["faculties"]) == 1
    assert len(all_pending.json()["subjects"]) == 2

    university_pending = await client.get(
        "/api/v1/moderation/catalog-proposals/universities",
        headers=admin_headers,
    )
    faculty_pending = await client.get(
        "/api/v1/moderation/catalog-proposals/faculties",
        headers=moderator_headers,
    )
    subject_pending = await client.get(
        "/api/v1/moderation/catalog-proposals/subjects",
        headers=moderator_headers,
    )
    assert university_pending.status_code == 200
    assert faculty_pending.status_code == 200
    assert subject_pending.status_code == 200

    approve_university = await client.patch(
        f"/api/v1/moderation/catalog-proposals/universities/{university_create.json()['id']}/approve",
        headers=admin_headers,
        json={"canonical_name": "Approved University", "note": "Looks valid"},
    )
    approve_faculty = await client.patch(
        f"/api/v1/moderation/catalog-proposals/faculties/{faculty_create.json()['id']}/approve",
        headers=moderator_headers,
        json={"canonical_name": "Approved Faculty", "note": "Accepted"},
    )
    reject_subject = await client.patch(
        f"/api/v1/moderation/catalog-proposals/subjects/{subject_reject_create.json()['id']}/reject",
        headers=moderator_headers,
        json={"reason": "duplicate", "note": "Covered by another subject"},
    )
    map_subject = await client.patch(
        f"/api/v1/moderation/catalog-proposals/subjects/{subject_map_create.json()['id']}/map-existing",
        headers=moderator_headers,
        json={"target_id": existing_subject.id, "note": "Map to canonical subject"},
    )

    assert approve_university.status_code == 200
    assert approve_university.json()["status"] == ProposalStatus.APPROVED.value
    assert approve_faculty.status_code == 200
    assert approve_faculty.json()["status"] == ProposalStatus.APPROVED.value
    assert reject_subject.status_code == 200
    assert reject_subject.json()["status"] == ProposalStatus.REJECTED.value
    assert map_subject.status_code == 200
    assert map_subject.json()["status"] == ProposalStatus.APPROVED.value

    approved_university = await session.scalar(
        select(UniversityProposal).where(UniversityProposal.id == university_create.json()["id"])
    )
    approved_faculty = await session.scalar(
        select(FacultyProposal).where(FacultyProposal.id == faculty_create.json()["id"])
    )
    rejected_subject = await session.scalar(
        select(SubjectProposal).where(SubjectProposal.id == subject_reject_create.json()["id"])
    )
    mapped_subject = await session.scalar(
        select(SubjectProposal).where(SubjectProposal.id == subject_map_create.json()["id"])
    )
    assert approved_university is not None and approved_university.approved_university_id is not None
    assert approved_faculty is not None and approved_faculty.approved_faculty_id is not None
    assert rejected_subject is not None and rejected_subject.status == ProposalStatus.REJECTED
    assert mapped_subject is not None and mapped_subject.approved_subject_id == existing_subject.id


@pytest.mark.asyncio
async def test_admin_endpoints_cover_catalog_user_scope_report_and_dashboard_flows(client, session):
    base_university = await seed_university(session, "Base University")
    base_faculty = await seed_faculty(session, base_university.id, "Base Faculty")
    base_subject = await seed_subject(session, base_faculty.id, "Base Subject", 2)

    admin = await seed_user(session, base_university.id, "admin@example.com", role=UserRole.ADMIN)
    managed_user = await seed_user(session, base_university.id, "managed@example.com")
    reporter = await seed_user(session, base_university.id, "reporter@example.com")
    uploader = await seed_user(session, base_university.id, "uploader@example.com")
    admin_headers = access_headers(admin)

    created_university = await client.post(
        "/api/v1/admin/universities",
        headers=admin_headers,
        json={"name": "Created University"},
    )
    assert created_university.status_code == 200
    created_university_id = created_university.json()["id"]

    updated_university = await client.patch(
        f"/api/v1/admin/universities/{created_university_id}",
        headers=admin_headers,
        json={"name": "Updated University"},
    )
    assert updated_university.status_code == 200
    assert updated_university.json()["name"] == "Updated University"

    created_faculty = await client.post(
        "/api/v1/admin/faculties",
        headers=admin_headers,
        json={"university_id": created_university_id, "name": "Created Faculty"},
    )
    assert created_faculty.status_code == 200
    created_faculty_id = created_faculty.json()["id"]

    updated_faculty = await client.patch(
        f"/api/v1/admin/faculties/{created_faculty_id}",
        headers=admin_headers,
        json={"name": "Updated Faculty"},
    )
    assert updated_faculty.status_code == 200
    assert updated_faculty.json()["name"] == "Updated Faculty"

    created_subject = await client.post(
        "/api/v1/admin/subjects",
        headers=admin_headers,
        json={"faculty_id": created_faculty_id, "name": "Created Subject", "semester": 1},
    )
    assert created_subject.status_code == 200
    created_subject_id = created_subject.json()["id"]

    updated_subject = await client.patch(
        f"/api/v1/admin/subjects/{created_subject_id}",
        headers=admin_headers,
        json={"name": "Updated Subject", "semester": 2},
    )
    assert updated_subject.status_code == 200
    assert updated_subject.json()["name"] == "Updated Subject"

    users_response = await client.get("/api/v1/admin/users", headers=admin_headers, params={"q": "managed"})
    assert users_response.status_code == 200
    assert users_response.json()["total"] >= 1

    user_detail = await client.get(f"/api/v1/admin/users/{managed_user.id}", headers=admin_headers)
    assert user_detail.status_code == 200
    assert user_detail.json()["email"] == managed_user.email

    user_update = await client.patch(
        f"/api/v1/admin/users/{managed_user.id}",
        headers=admin_headers,
        json={"full_name": "Managed User Updated"},
    )
    assert user_update.status_code == 200
    assert user_update.json()["full_name"] == "Managed User Updated"

    user_status = await client.patch(
        f"/api/v1/admin/users/{managed_user.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert user_status.status_code == 200
    assert user_status.json()["is_active"] is False

    user_verify = await client.patch(
        f"/api/v1/admin/users/{managed_user.id}/verify",
        headers=admin_headers,
        json={"is_verified": True},
    )
    assert user_verify.status_code == 200
    assert user_verify.json()["is_verified"] is True

    user_role = await client.patch(
        f"/api/v1/admin/users/{managed_user.id}/role",
        headers=admin_headers,
        params={"role": "moderator"},
    )
    assert user_role.status_code == 200
    assert user_role.json()["role"] == "moderator"

    assign_scope = await client.post(
        f"/api/v1/admin/users/{managed_user.id}/moderator-scopes",
        headers=admin_headers,
        json={"university_id": base_university.id},
    )
    assert assign_scope.status_code == 200
    scope_id = assign_scope.json()["scope_id"]

    user_scopes = await client.get(
        f"/api/v1/admin/users/{managed_user.id}/moderator-scopes",
        headers=admin_headers,
    )
    all_scopes = await client.get("/api/v1/admin/moderators/scopes", headers=admin_headers)
    assert user_scopes.status_code == 200
    assert len(user_scopes.json()) == 1
    assert all_scopes.status_code == 200
    assert any(item["scope_id"] == base_university.id for item in all_scopes.json())

    delete_scope = await client.delete(
        f"/api/v1/admin/users/{managed_user.id}/moderator-scopes/{scope_id}",
        headers=admin_headers,
    )
    assert delete_scope.status_code == 200

    material = await seed_material(
        session,
        uploader,
        base_subject.id,
        "Reported Material",
        status=MaterialStatus.APPROVED,
    )
    open_report = await seed_report(session, material.id, reporter.id, reason="copyright")
    dismissed_report = await seed_report(session, material.id, reporter.id, reason="spam")

    reports_response = await client.get("/api/v1/admin/reports", headers=admin_headers)
    assert reports_response.status_code == 200
    assert reports_response.json()["total"] == 2

    report_detail = await client.get(f"/api/v1/admin/reports/{open_report.id}", headers=admin_headers)
    assert report_detail.status_code == 200
    assert report_detail.json()["reason"] == "copyright"

    report_update = await client.patch(
        f"/api/v1/admin/reports/{open_report.id}",
        headers=admin_headers,
        json={"resolution_note": "Investigating"},
    )
    assert report_update.status_code == 200
    assert report_update.json()["resolution_note"] == "Investigating"

    resolve_report = await client.post(
        f"/api/v1/admin/reports/{open_report.id}/resolve",
        headers=admin_headers,
        json={"resolution_note": "Resolved"},
    )
    dismiss_report = await client.post(
        f"/api/v1/admin/reports/{dismissed_report.id}/dismiss",
        headers=admin_headers,
        json={"resolution_note": "Dismissed"},
    )
    assert resolve_report.status_code == 200
    assert resolve_report.json()["status"] == ReportStatus.RESOLVED.value
    assert dismiss_report.status_code == 200
    assert dismiss_report.json()["status"] == ReportStatus.DISMISSED.value

    audit_logs = await client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert audit_logs.status_code == 200
    assert audit_logs.json()["total"] >= 1

    dashboard_summary = await client.get("/api/v1/admin/dashboard/summary", headers=admin_headers)
    dashboard_charts = await client.get("/api/v1/admin/dashboard/charts", headers=admin_headers)
    assert dashboard_summary.status_code == 200
    assert dashboard_summary.json()["total_materials"] >= 1
    assert dashboard_charts.status_code == 200
    assert "top_universities" in dashboard_charts.json()
    assert "top_material_types" in dashboard_charts.json()

    delete_subject = await client.delete(
        f"/api/v1/admin/subjects/{created_subject_id}",
        headers=admin_headers,
    )
    delete_faculty = await client.delete(
        f"/api/v1/admin/faculties/{created_faculty_id}",
        headers=admin_headers,
    )
    delete_university = await client.delete(
        f"/api/v1/admin/universities/{created_university_id}",
        headers=admin_headers,
    )
    assert delete_subject.status_code == 200
    assert delete_faculty.status_code == 200
    assert delete_university.status_code == 200

    audit_rows = (await session.execute(select(AuditLog))).scalars().all()
    assert any(row.action == "report_resolved" for row in audit_rows)
