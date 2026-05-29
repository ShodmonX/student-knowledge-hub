from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.cache import CacheService, NullCacheBackend
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    PermissionDenied,
    PolicyViolation,
    ResourceNotFound,
    ValidationAppError,
)
from app.core.security import create_refresh_token
from app.modules.audit.models import AuditLog
from app.modules.auth.models import EmailOutbox, PasswordResetToken, RefreshTokenSession
from app.modules.catalog_proposals.enums import ProposalEntityType, ProposalStatus
from app.modules.catalog.models import Subject
from app.modules.catalog_proposals.models import CatalogProposalLog, FacultyProposal, SubjectProposal, UniversityProposal
from app.modules.community.models import MaterialRating
from app.modules.materials.enums import MaterialStatus, MaterialType, RejectReason
from app.modules.materials.models import Material, MaterialFile
from app.modules.notifications.models import Notification
from app.modules.tags.models import Tag
from app.modules.users.enums import UserRole
from app.modules.users.models import UserPreference
from app.modules.auth.schemas import ForgotPasswordRequest, LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, ResetPasswordRequest
from app.modules.catalog_proposals.schemas import (
    FacultyProposalCreate,
    HomeUniversityUpdateRequest,
    ProposalApproveRequest,
    ProposalRejectRequest,
    SubjectProposalCreate,
    UniversityProposalCreate,
)
from app.modules.materials.schemas import MaterialCreate, MaterialReportCreate, MaterialUpdate
from app.modules.moderation.schemas import MoveSubjectRequest
from app.modules.users.schemas import UserPreferenceUpdate, UserUpdateMe
from app.infrastructure.storage.service import (
    LocalStorageProvider,
    SpacesStorageProvider,
    StorageDownload,
    StorageService,
)
from app.modules.auth.service import AuthService
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.materials.service import MaterialService
from app.modules.users.service import UserService
from app.shared.dependencies.pagination import get_pagination_params
from app.shared.services.policy import PolicyService
from app.utils.files import detect_file_kind, detect_mime_type, get_extension, validate_file_signature
from app.utils.hashing import sha256_text
from tests.helpers import (
    add_faculty_scope,
    add_subject_scope,
    add_university_scope,
    docx_upload,
    empty_upload,
    pdf_upload,
    png_upload,
    seed_faculty,
    seed_material,
    seed_subject,
    seed_university,
    seed_user,
)


def _extract_token_from_email(message: EmailOutbox) -> str:
    for word in message.text_body.split():
        if "token=" in word:
            return parse_qs(urlparse(word).query)["token"][0]
    raise AssertionError("email token link not found")


@pytest.mark.asyncio
async def test_auth_service_direct_covers_refresh_replay_logout_and_reset_edges(session):
    university = await seed_university(session, "Branch Auth University")
    user = await seed_user(session, university.id, "branch-auth@example.com")
    other_user = await seed_user(session, university.id, "branch-other@example.com")
    service = AuthService(session)

    login = await service.login(LoginRequest(email=user.email, password="password123"))
    sessions = await service.list_sessions(user)
    assert len(sessions) == 1

    refreshed = await service.refresh(RefreshRequest(refresh_token=login.refresh_token))
    assert refreshed.refresh_token != login.refresh_token

    with pytest.raises(AuthenticationError):
        await service.refresh(RefreshRequest(refresh_token=login.refresh_token))

    with pytest.raises(AuthenticationError):
        await service.refresh(
            RefreshRequest(refresh_token=create_refresh_token("missing-user", UserRole.STUDENT.value))
        )

    second_login = await service.login(LoginRequest(email=user.email, password="password123"))
    second_session = await session.scalar(
        select(RefreshTokenSession)
        .where(RefreshTokenSession.token_hash == sha256_text(second_login.refresh_token))
    )
    assert second_session is not None
    second_session.user_id = other_user.id
    await session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(RefreshRequest(refresh_token=second_login.refresh_token))

    third_login = await service.login(LoginRequest(email=user.email, password="password123"))
    third_session = await session.scalar(
        select(RefreshTokenSession)
        .where(RefreshTokenSession.token_hash == sha256_text(third_login.refresh_token))
    )
    assert third_session is not None
    third_session.token_hash = "0" * 64
    await session.commit()
    with pytest.raises(AuthenticationError):
        await service.refresh(RefreshRequest(refresh_token=third_login.refresh_token))

    assert (
        await service.forgot_password(ForgotPasswordRequest(email="missing@example.com"))
    )["message"].startswith("Agar akkaunt mavjud bo'lsa")

    logout_login = await service.login(LoginRequest(email=user.email, password="password123"))
    assert await service.logout(LogoutRequest(refresh_token=logout_login.refresh_token)) == {
        "message": "Tizimdan chiqildi"
    }

    with pytest.raises(ResourceNotFound):
        await service.revoke_session(user, "missing-session")

    active_login = await service.login(LoginRequest(email=user.email, password="password123"))
    active_session = await session.scalar(
        select(RefreshTokenSession)
        .where(RefreshTokenSession.token_hash == sha256_text(active_login.refresh_token))
    )
    assert active_session is not None
    revoked = await service.revoke_session(user, active_session.id)
    assert revoked["message"] == "Sessiya bekor qilindi"

    await service.login(LoginRequest(email=user.email, password="password123"))
    logout_all = await service.logout_all(user)
    assert logout_all["message"] == "Barcha sessiyalar bekor qilindi"


@pytest.mark.asyncio
async def test_catalog_proposal_service_covers_validation_pending_scope_and_review_paths(session):
    university = await seed_university(session, "Proposal University")
    second_university = await seed_university(session, "Proposal University 2")
    faculty = await seed_faculty(session, university.id, "Proposal Faculty")
    other_faculty = await seed_faculty(session, second_university.id, "Other Proposal Faculty")
    subject = await seed_subject(session, faculty.id, "Proposal Subject", 2)
    admin = await seed_user(session, university.id, "proposal-admin@example.com", role=UserRole.ADMIN)
    moderator = await seed_user(session, university.id, "proposal-mod@example.com", role=UserRole.MODERATOR)
    outsider = await seed_user(session, university.id, "proposal-outsider@example.com", role=UserRole.MODERATOR)
    student = await seed_user(session, university.id, "proposal-student@example.com")
    service = CatalogProposalService(session)

    with pytest.raises(ValidationAppError):
        await service.create_university_proposal(UniversityProposalCreate(name="  "), student)
    with pytest.raises(ResourceNotFound):
        await service.create_faculty_proposal(
            FacultyProposalCreate(university_id="missing-university", name="Missing Faculty"),
            student,
        )
    with pytest.raises(ResourceNotFound):
        await service.create_subject_proposal(
            SubjectProposalCreate(faculty_id="missing-faculty", name="Missing Subject", semester=1),
            student,
        )

    university_proposal = await service.create_university_proposal(
        UniversityProposalCreate(name="Brand New University"),
        student,
    )
    faculty_proposal = await service.create_faculty_proposal(
        FacultyProposalCreate(university_id=university.id, name="Brand New Faculty"),
        student,
    )
    subject_proposal = await service.create_subject_proposal(
        SubjectProposalCreate(faculty_id=faculty.id, name="Brand New Subject", semester=3),
        student,
    )

    with pytest.raises(ConflictError):
        await service.create_faculty_proposal(
            FacultyProposalCreate(university_id=university.id, name=" brand new faculty "),
            student,
        )
    with pytest.raises(ConflictError):
        await service.create_subject_proposal(
            SubjectProposalCreate(faculty_id=faculty.id, name="brand new subject", semester=3),
            student,
        )

    listed = await service.list_user_proposals(student, UniversityProposal)
    assert len(listed) == 1 and listed[0].id == university_proposal.id

    with pytest.raises(PermissionDenied):
        await service.approve_university(university_proposal.id, moderator, ProposalApproveRequest())

    pending_for_admin = await service.list_pending(admin)
    assert len(pending_for_admin["universities"]) == 1
    assert len(pending_for_admin["faculties"]) == 1
    assert len(pending_for_admin["subjects"]) == 1

    await add_university_scope(session, moderator.id, university.id)
    with pytest.raises(PermissionDenied):
        await service.list_pending(moderator)
    pending_for_uni_mod = await service.list_pending(moderator, "faculties")
    assert {item.id for item in pending_for_uni_mod["faculties"]} == {faculty_proposal.id}
    subject_pending_for_uni_mod = await service.list_pending(moderator, "subjects")
    assert {item.id for item in subject_pending_for_uni_mod["subjects"]} == {subject_proposal.id}

    approved_university = await service.approve_university(
        university_proposal.id,
        admin,
        ProposalApproveRequest(canonical_name="Canonical University"),
    )
    assert approved_university.status == ProposalStatus.APPROVED
    with pytest.raises(ConflictError):
        await service.reject_university(
            university_proposal.id,
            admin,
            ProposalRejectRequest(reason="duplicate", note="already approved"),
        )
    with pytest.raises(ConflictError):
        await service.map_existing_university(university_proposal.id, admin, "missing", None)
    missing_target_university_proposal = await service.create_university_proposal(
        UniversityProposalCreate(name="Missing Target University"),
        student,
    )
    with pytest.raises(ResourceNotFound):
        await service.map_existing_university(
            missing_target_university_proposal.id,
            admin,
            "missing",
            None,
        )

    approved_faculty = await service.approve_faculty(
        faculty_proposal.id,
        moderator,
        ProposalApproveRequest(canonical_name="Canonical Faculty"),
    )
    assert approved_faculty.status == ProposalStatus.APPROVED

    foreign_proposal = await service.create_faculty_proposal(
        FacultyProposalCreate(university_id=second_university.id, name="Foreign Faculty Proposal"),
        student,
    )
    with pytest.raises(PermissionDenied):
        await service.reject_faculty(
            foreign_proposal.id,
            moderator,
            ProposalRejectRequest(reason="wrong_parent", note="out of scope"),
        )
    with pytest.raises(ResourceNotFound):
        await service.map_existing_faculty(foreign_proposal.id, admin, "missing-faculty", None)

    subject_scope_user = await seed_user(
        session,
        university.id,
        "proposal-subject-mod@example.com",
        role=UserRole.MODERATOR,
    )
    await add_subject_scope(session, subject_scope_user.id, subject.id)
    approved_subject = await service.approve_subject(
        subject_proposal.id,
        subject_scope_user,
        ProposalApproveRequest(canonical_name="Canonical Subject", canonical_semester=4),
    )
    assert approved_subject.status == ProposalStatus.APPROVED
    with pytest.raises(ConflictError):
        await service.reject_subject(
            subject_proposal.id,
            subject_scope_user,
            ProposalRejectRequest(reason="duplicate", note="already approved"),
        )
    with pytest.raises(ConflictError):
        await service.map_existing_subject(subject_proposal.id, admin, "missing-subject", None)
    missing_target_subject_proposal = await service.create_subject_proposal(
        SubjectProposalCreate(faculty_id=other_faculty.id, name="Missing Target Subject", semester=5),
        student,
    )
    with pytest.raises(ResourceNotFound):
        await service.map_existing_subject(
            missing_target_subject_proposal.id,
            admin,
            "missing-subject",
            None,
        )

    faculty_scope_user = await seed_user(
        session,
        university.id,
        "proposal-faculty-mod@example.com",
        role=UserRole.MODERATOR,
    )
    await add_faculty_scope(session, faculty_scope_user.id, faculty.id)
    faculty_scope_pending = await service.list_pending(faculty_scope_user, "subjects")
    assert faculty_scope_pending["subjects"] == []
    assert await service.list_pending(outsider, "subjects") == {"universities": [], "faculties": [], "subjects": []}

    logs = (
        await session.execute(select(CatalogProposalLog).where(CatalogProposalLog.entity_type == ProposalEntityType.SUBJECT))
    ).scalars().all()
    assert any(log.action == "approved" for log in logs)


@pytest.mark.asyncio
async def test_material_service_direct_covers_preview_download_cache_and_editing_paths(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_auth_service_direct_covers_register_and_reset_happy_paths(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_enabled", True)
    university = await seed_university(session, "Register Service University")
    service = AuthService(session)

    registered = await service.register(
        RegisterRequest(
            full_name="Registered User",
            email="register-service@example.com",
            password="password123",
            university_id=university.id,
        )
    )
    assert registered.email == "register-service@example.com"

    forgot = await service.forgot_password(ForgotPasswordRequest(email=registered.email))
    assert forgot["message"].startswith("Agar akkaunt mavjud bo'lsa")

    reset_token = await session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.user_id == registered.id)
    )
    assert reset_token is not None
    reset_email = await session.scalar(
        select(EmailOutbox)
        .where(EmailOutbox.recipient_email == registered.email)
        .order_by(EmailOutbox.created_at.desc())
    )
    assert reset_email is not None
    raw_reset_token = _extract_token_from_email(reset_email)
    assert reset_token.token == sha256_text(raw_reset_token)

    completed = await service.reset_password(
        ResetPasswordRequest(token=raw_reset_token, new_password="updated-password123")
    )
    assert completed["message"] == "Parol tiklandi"

    relogin = await service.login(
        LoginRequest(email=registered.email, password="updated-password123")
    )
    assert relogin.access_token


@pytest.mark.asyncio
async def test_material_service_direct_covers_submission_tags_reporting_and_collections(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    university = await seed_university(session, "Extra Material University")
    faculty = await seed_faculty(session, university.id, "Extra Material Faculty")
    subject = await seed_subject(session, faculty.id, "Extra Material Subject", 2)
    other_subject = await seed_subject(session, faculty.id, "Extra Material Other Subject", 3)
    owner = await seed_user(session, university.id, "extra-owner@example.com")
    other_user = await seed_user(session, university.id, "extra-viewer@example.com")
    moderator = await seed_user(session, university.id, "extra-mod@example.com", role=UserRole.MODERATOR)
    service = MaterialService(session)

    draft = await service.create_draft(
        MaterialCreate(
            title="Submission Material",
            description="draft",
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            semesters=[1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        owner,
    )

    with pytest.raises(ValidationAppError):
        await service.submit(draft.id, owner)
    with pytest.raises(ConflictError):
        await service.withdraw(draft.id, owner)
    with pytest.raises(PermissionDenied):
        await service.get_material_for_view(draft.id, other_user)
    assert (await service.get_material_for_view(draft.id, owner)).id == draft.id
    assert (await service.get_material_for_view(draft.id, moderator)).id == draft.id
    with pytest.raises(ResourceNotFound):
        await service.get_material_for_view("missing-material", owner)

    attached = await service.attach_files(draft.id, owner, [png_upload("submit.png", b"Z")], [0])
    draft.primary_file_id = attached[0].id
    draft.cover_file_id = attached[0].id
    draft.file_count = 1
    await session.commit()

    submitted = await service.submit(draft.id, owner)
    assert submitted.status == MaterialStatus.PENDING_REVIEW
    with pytest.raises(ConflictError):
        await service.update_material(draft.id, MaterialUpdate(title="Nope"), owner)

    withdrawn = await service.withdraw(draft.id, owner)
    assert withdrawn.status == MaterialStatus.DRAFT
    updated = await service.update_material(
        draft.id,
        MaterialUpdate(title="Updated Draft", subject_id=other_subject.id),
        owner,
    )
    assert updated.title == "Updated Draft"
    assert updated.subject_id == other_subject.id

    tag = Tag(name="Tag One", slug="tag-one")
    session.add(tag)
    await session.commit()

    tagged = await service.attach_tag(draft.id, tag.id, owner)
    assert any(item.id == tag.id for item in tagged.tags)
    tagged_again = await service.attach_tag(draft.id, tag.id, owner)
    assert len(tagged_again.tags) == 1
    detached = await service.detach_tag(draft.id, tag.id, owner)
    assert detached.tags == []
    with pytest.raises(ResourceNotFound):
        await service.attach_tag(draft.id, "missing-tag", owner)
    with pytest.raises(ResourceNotFound):
        await service.detach_tag(draft.id, tag.id, owner)

    draft.status = MaterialStatus.APPROVED
    draft.reviewed_at = datetime.now(UTC)
    session.add(draft)
    await session.commit()

    reported = await service.update_material(draft.id, MaterialUpdate(description="changed"), owner)
    assert reported.status == MaterialStatus.PENDING_REVIEW
    await session.refresh(draft)
    draft.status = MaterialStatus.APPROVED
    draft.reviewed_at = datetime.now(UTC)
    session.add(draft)
    await session.commit()

    other_approved = await seed_material(
        session,
        owner,
        other_subject.id,
        "Featured Material",
        status=MaterialStatus.APPROVED,
    )
    other_approved.download_count = 9
    other_approved.reviewed_at = datetime.now(UTC)
    session.add(other_approved)
    await session.commit()

    resources = await service.list_resources(draft.id)
    assert len(resources) == 1
    related = await service.list_related(draft.id)
    assert len(related) == 1
    assert related[0].id == other_approved.id
    featured = await service.list_featured()
    assert featured[0].id == other_approved.id

    await service.report_material(
        other_approved.id,
        MaterialReportCreate(reason="spam", details="service branch report"),
        other_user,
    )
    draft.status = MaterialStatus.REJECTED
    session.add(draft)
    await session.commit()
    with pytest.raises(ResourceNotFound):
        await service.report_material(draft.id, MaterialReportCreate(reason="spam", details=None), other_user)

    by_slug = await service.get_material_by_slug_for_view(other_approved.slug, other_user)
    assert by_slug.id == other_approved.id

    await service.delete_material(draft.id, owner)
    with pytest.raises(ResourceNotFound):
        await service.get_material_for_view(draft.id, owner)

    assert await service.cleanup_stale_drafts() == 0
    assert await service.list_for_user(owner)

    get_settings.cache_clear()

    university = await seed_university(session, "Material Service University")
    faculty = await seed_faculty(session, university.id, "Material Service Faculty")
    subject = await seed_subject(session, faculty.id, "Material Service Subject", 1)
    user = await seed_user(session, university.id, "material-service-owner@example.com")
    moderator = await seed_user(session, university.id, "material-service-mod@example.com", role=UserRole.MODERATOR)
    service = MaterialService(session)
    user_id = user.id
    moderator_id = moderator.id

    with pytest.raises(ResourceNotFound):
        await service.create_draft(
            MaterialCreate(
                title="Missing Subject",
                description=None,
                material_type=MaterialType.NOTES,
                subject_id="missing-subject",
                semesters=[1],
                cover_file_id=None,
                primary_file_id=None,
            ),
            user,
        )

    first = await service.create_draft(
        MaterialCreate(
            title="Repeated Title",
            description="one",
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            semesters=[1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    second = await service.create_draft(
        MaterialCreate(
            title="Repeated Title",
            description="two",
            material_type=MaterialType.SLIDES,
            subject_id=subject.id,
            semesters=[1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    assert second.slug.endswith("-2")
    first_id = first.id
    second_id = second.id

    with pytest.raises(ValidationAppError):
        await service.attach_files(first_id, user, [png_upload("one.png", b"A")], [])

    service.settings.upload_max_file_count = 0
    with pytest.raises(ValidationAppError):
        await service.attach_files(first_id, user, [png_upload("one.png", b"A")], [0])
    service.settings.upload_max_file_count = 10

    service.settings.upload_max_total_size = 1
    with pytest.raises(ValidationAppError):
        await service.attach_files(first_id, user, [png_upload("big.png", b"A")], [0])
    service.settings.upload_max_total_size = 50 * 1024 * 1024

    user = await session.get(type(user), user_id)
    assert user is not None
    pdf_files = await service.attach_files(second_id, user, [pdf_upload(pages=4)], [0])
    assert pdf_files[0].preview_storage_key is not None
    assert pdf_files[0].preview_page_count == 2
    pdf_file_id = pdf_files[0].id

    second = await session.get(Material, second_id)
    assert second is not None
    second.status = MaterialStatus.APPROVED
    second.primary_file_id = pdf_file_id
    second.cover_file_id = pdf_file_id
    second.file_count = 1
    session.add(second)
    await session.commit()
    session.expire_all()

    preview_download, preview_type = await service.prepare_preview(second_id, pdf_file_id)
    assert preview_download.local_path is not None
    assert preview_download.local_path.exists()

    docx_material = await service.create_draft(
        MaterialCreate(
            title="Docx Material",
            description=None,
            material_type=MaterialType.BOOK,
            subject_id=subject.id,
            semesters=[1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    docx_files = await service.attach_files(docx_material.id, user, [docx_upload()], [0])
    docx_material.status = MaterialStatus.APPROVED
    docx_material.primary_file_id = docx_files[0].id
    docx_material.file_count = 1
    session.add(docx_material)
    await session.commit()
    with pytest.raises(AuthenticationError):
        await service.prepare_preview(docx_material.id, docx_files[0].id)

    docx_file = await session.get(MaterialFile, docx_files[0].id)
    assert docx_file is not None
    docx_file.is_previewable = False
    await session.commit()
    with pytest.raises(PermissionDenied):
        await service.prepare_preview(docx_material.id, docx_files[0].id, user)

    with pytest.raises(ResourceNotFound):
        await service.prepare_download(second_id, "missing-file", moderator)

    local_file = await session.get(MaterialFile, pdf_file_id)
    assert local_file is not None
    await service.storage.delete(local_file.storage_key)
    with pytest.raises(ResourceNotFound):
        await service.prepare_download(second_id, local_file.id, moderator)

    pending_material = await seed_material(session, user, subject.id, "Pending Access", status=MaterialStatus.PENDING_REVIEW)
    user = await session.get(type(user), user_id)
    moderator = await session.get(type(moderator), moderator_id)
    assert user is not None and moderator is not None
    restricted_context = await service.get_material_access_context(pending_material, None)
    owner_context = await service.get_material_access_context(pending_material, user)
    moderator_context = await service.get_material_access_context(pending_material, moderator)
    second = await session.get(Material, second_id)
    assert second is not None
    public_context = await service.get_material_access_context(second, None)
    auth_context = await service.get_material_access_context(second, user)
    assert restricted_context["access_level"] == "restricted"
    assert owner_context["access_level"] == "owner"
    assert moderator_context["access_level"] == "moderator"
    assert public_context["preview_page_limit"] == 2
    assert auth_context["can_download"] is True

    await service.cache.set("materials:trending_ids", [second_id], 60)
    trending = await service.list_trending()
    assert second_id in {item.id for item in trending}
    await service.cache.set("materials:stats_summary", {"cached": True}, 60)
    summary = await service.stats_summary()
    assert summary["total_materials"] >= 1
    assert await service.get_rating_snapshot([]) == {}

    session.add(MaterialRating(material_id=second_id, user_id=user.id, value=4))
    await session.commit()
    rating_snapshot = await service.get_rating_snapshot([second_id])
    assert rating_snapshot[second_id][0] == 4.0

    third = await service.create_draft(
        MaterialCreate(
            title="Delete File Material",
            description=None,
            material_type=MaterialType.NOTES,
            subject_id=subject.id,
            semesters=[1],
            cover_file_id=None,
            primary_file_id=None,
        ),
        user,
    )
    third_files = await service.attach_files(third.id, user, [png_upload("delete.png", b"B")], [0])
    third.cover_file_id = third_files[0].id
    third.primary_file_id = third_files[0].id
    await session.commit()

    async def flaky_delete(storage_key: str) -> None:
        raise RuntimeError(storage_key)

    monkeypatch.setattr(service.storage, "delete", flaky_delete)
    refreshed = await service.delete_file(third.id, third_files[0].id, user)
    assert refreshed.file_count == 0

    with pytest.raises(ValidationAppError):
        await service.reorder_files(first_id, ["missing-id"], user)
    with pytest.raises(ValidationAppError):
        await service.update_file_selection(second_id, pdf_file_id, None, None, user)

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_user_service_storage_cache_utils_and_small_modules(session, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    university = await seed_university(session, "User Service University")
    faculty = await seed_faculty(session, university.id, "User Service Faculty")
    subject = await seed_subject(session, faculty.id, "User Service Subject", 1)
    user = await seed_user(session, university.id, "user-service@example.com")
    service = UserService(session)

    with pytest.raises(ResourceNotFound):
        await service.get_user("missing-user")

    updated_user = await service.update_me(user, UserUpdateMe(full_name="Service Updated User"))
    assert updated_user.full_name == "Service Updated User"

    with pytest.raises(ConflictError):
        await service.change_password(
            user,
            type("Payload", (), {"current_password": "wrong", "new_password": "changed-password123"})(),
        )

    preference = await service.get_preferences(user)
    assert isinstance(preference, UserPreference)
    updated_pref = await service.update_preferences(
        user,
        UserPreferenceUpdate(theme="dark", language="uz"),
    )
    assert updated_pref.theme == "dark"

    notification = Notification(user_id=user.id, title="Hello", body="World")
    session.add(notification)
    await session.commit()
    notifications = await service.list_notifications(user)
    assert len(notifications) == 1
    read_notification = await service.mark_notification_read(notification.id, user)
    assert read_notification.is_read is True
    assert await service.mark_all_notifications_read(user) == 1
    with pytest.raises(ResourceNotFound):
        await service.mark_notification_read("missing-notification", user)

    material = await seed_material(session, user, subject.id, "Saved Material", status=MaterialStatus.APPROVED)
    await service.save_material(material.id, user)
    await service.save_material(material.id, user)
    saved = await service.list_saved_materials(user)
    assert len(saved) == 1
    await service.remove_saved_material(material.id, user)
    await service.clear_saved_materials(user)
    listed_materials, total = await service.list_user_materials(user, type("Q", (), {"page": 1, "page_size": 10, "q": None, "subject_id": None, "faculty_id": None, "university_id": None, "material_type": None, "semester": None, "course": None, "status": None, "only_approved": None, "is_public": None, "uploaded_by": None, "download_count_gte": None, "file_format": None, "sort": "created_at_desc"})())
    assert total >= 1
    assert any(item.id == material.id for item in listed_materials)

    assert get_extension("file.PDF") == "pdf"
    assert detect_file_kind("png").value == "image"
    assert detect_file_kind("txt").value == "document"
    assert detect_mime_type("unknown") == "application/octet-stream"

    bad_png = tmp_path / "bad.png"
    bad_png.write_bytes(b"not-a-png")
    with pytest.raises(ValidationAppError):
        validate_file_signature("png", b"not-a-png", bad_png)
    with pytest.raises(ValidationAppError):
        validate_file_signature("docx", b"PK\x03\x04", bad_png)

    provider = LocalStorageProvider(str(tmp_path / "storage"))
    stored = await provider.save(png_upload("local.png", b"C"), "material-1", max_file_size=1024 * 1024)
    assert await provider.exists(stored.storage_key) is True
    download = await provider.resolve_for_download(stored.storage_key)
    assert download.local_path is not None and download.local_path.exists()
    assert await provider.read_bytes(stored.storage_key)
    await provider.delete(stored.storage_key)
    assert await provider.exists(stored.storage_key) is False
    with pytest.raises(ResourceNotFound):
        await provider.resolve_for_download("missing-key")
    with pytest.raises(ResourceNotFound):
        await provider.read_bytes("missing-key")
    with pytest.raises(ValidationAppError):
        await provider.save(empty_upload(), "material-2", max_file_size=1024)

    class FakeClientError(Exception):
        pass

    class FakeBody:
        def read(self):
            return b"remote-bytes"

    class FakeS3Client:
        def __init__(self):
            self.objects: dict[str, bytes] = {}

        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            self.objects[key] = Path(filename).read_bytes()

        def put_object(self, Bucket, Key, Body, ContentType=None):
            self.objects[Key] = Body

        def delete_object(self, Bucket, Key):
            self.objects.pop(Key, None)

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            if Params["Key"] == "missing-key":
                raise FakeClientError("missing")
            return f"https://example.test/{Params['Key']}"

        def head_object(self, Bucket, Key):
            if Key not in self.objects:
                raise FakeClientError("missing")
            return {"Key": Key}

        def get_object(self, Bucket, Key):
            if Key not in self.objects:
                raise FakeClientError("missing")
            return {"Body": FakeBody()}

    fake_client = FakeS3Client()

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            return fake_client

    import app.infrastructure.storage.service as storage_module

    monkeypatch.setattr(storage_module, "boto3", FakeBoto3())
    monkeypatch.setattr(storage_module, "ClientError", FakeClientError)
    monkeypatch.setattr(storage_module, "BotoCoreError", FakeClientError)

    spaces = SpacesStorageProvider(
        bucket="bucket",
        region="fra1",
        endpoint_url="https://fra1.digitaloceanspaces.com",
        access_key_id="key",
        secret_access_key="secret",
        presigned_expiry_seconds=60,
    )
    remote = await spaces.save(png_upload("remote.png", b"D"), "material-3", max_file_size=1024 * 1024)
    assert await spaces.exists(remote.storage_key) is True
    assert (await spaces.resolve_for_download(remote.storage_key)).redirect_url is not None
    assert await spaces.read_bytes(remote.storage_key) == b"remote-bytes"
    await spaces.save_bytes(b"hello", "custom-key", "text/plain")
    await spaces.delete("custom-key")
    assert await spaces.exists("custom-key") is False
    with pytest.raises(ResourceNotFound):
        await spaces.resolve_for_download("missing-key")
    with pytest.raises(ResourceNotFound):
        await spaces.read_bytes("missing-key")

    monkeypatch.setattr(
        storage_module,
        "get_settings",
        lambda: SimpleNamespace(
            storage_backend="s3",
            s3_bucket=None,
            s3_region=None,
            s3_access_key_id=None,
            s3_secret_access_key=None,
            s3_endpoint_url=None,
            s3_presigned_expiry_seconds=60,
            storage_root=str(tmp_path / "unused-storage"),
        ),
    )
    with pytest.raises(RuntimeError):
        StorageService()

    cache = CacheService()
    await cache.initialize(None)
    assert isinstance(cache.backend, NullCacheBackend)
    await cache.set("materials:1", {"ok": True}, 60)
    assert await cache.get("materials:1") is None
    await cache.invalidate("materials:1")
    assert await cache.get("materials:1") is None
    await cache.set("admin:dashboard:1", 1, 60)
    await cache.set("admin:dashboard:2", 2, 60)
    await cache.invalidate_prefix("admin:dashboard:")
    assert await cache.get("admin:dashboard:1") is None

    from app.core import cache as cache_module

    async def broken_connect(self):
        raise cache_module.RedisError("redis down")

    monkeypatch.setattr(cache_module.RedisCacheBackend, "connect", broken_connect)
    await cache.initialize("redis://localhost:6379/0")
    assert isinstance(cache.backend, NullCacheBackend)
    await cache.close()

    page = get_pagination_params(page=2, page_size=999)
    assert page.page == 2
    assert page.page_size == get_settings().max_page_size

    policy = PolicyService()
    with pytest.raises(PolicyViolation):
        policy.validate_report_reason("   ")
    policy.validate_report_reason("spam")

    get_settings.cache_clear()
