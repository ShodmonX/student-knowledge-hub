import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.catalog_proposals.schemas import FacultyProposalCreate, SubjectProposalCreate, UniversityProposalCreate
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.materials.enums import MaterialStatus, RejectReason
from app.modules.materials.service import MaterialService
from app.modules.telegram.enums import TelegramEventStatus, TelegramEventType
from app.modules.telegram.models import TelegramEventOutbox, TelegramLink
from app.modules.users.enums import UserRole
from tests.helpers import (
    add_faculty_scope,
    add_subject_scope,
    add_university_scope,
    internal_headers,
    seed_faculty,
    seed_material,
    seed_subject,
    seed_university,
    seed_user,
)


@pytest.mark.asyncio
async def test_user_registration_creates_admin_telegram_event(client, session):
    university = await seed_university(session, "Registration University")
    admin = await seed_user(session, university.id, email="reg-admin@example.com", role=UserRole.ADMIN)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "New Student",
            "email": "new-student@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    assert response.status_code == 201

    events = (
        await session.execute(
            select(TelegramEventOutbox).where(TelegramEventOutbox.event_type == TelegramEventType.USER_REGISTERED)
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].recipient_user_id == admin.id
    assert events[0].payload["user_id"] == response.json()["id"]


@pytest.mark.asyncio
async def test_user_registration_leaves_event_pending_for_background_worker(client, session):
    university = await seed_university(session, "Background Registration University")
    await seed_user(session, university.id, email="background-admin@example.com", role=UserRole.ADMIN)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Background Student",
            "email": "background-student@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )

    assert response.status_code == 201
    event = await session.scalar(
        select(TelegramEventOutbox).where(
            TelegramEventOutbox.event_type == TelegramEventType.USER_REGISTERED,
            TelegramEventOutbox.entity_id == response.json()["id"],
        )
    )
    assert event is not None
    assert event.status == TelegramEventStatus.PENDING
    assert event.attempt_count == 0


@pytest.mark.asyncio
async def test_proposal_creation_creates_events_for_relevant_recipients(session):
    university = await seed_university(session, "Proposal Event University")
    admin = await seed_user(session, university.id, email="proposal-admin@example.com", role=UserRole.ADMIN)
    moderator = await seed_user(
        session,
        university.id,
        email="proposal-moderator@example.com",
        role=UserRole.MODERATOR,
    )
    submitter = await seed_user(session, university.id, email="proposal-submit@example.com")
    faculty = await seed_faculty(session, university.id, "Event Faculty")
    subject = await seed_subject(session, faculty.id, "Event Subject", 2)
    await add_university_scope(session, moderator.id, university.id)
    await add_subject_scope(session, moderator.id, subject.id)

    service = CatalogProposalService(session)

    university_proposal = await service.create_university_proposal(
        UniversityProposalCreate(name="Third Campus", description="Need a new campus"),
        submitter,
    )
    faculty_proposal = await service.create_faculty_proposal(
        FacultyProposalCreate(university_id=university.id, name="Applied Science", description="Need new faculty"),
        submitter,
    )
    subject_proposal = await service.create_subject_proposal(
        SubjectProposalCreate(faculty_id=faculty.id, name="Astrophysics", semester=3, description="Need subject"),
        submitter,
    )

    events = (
        await session.execute(select(TelegramEventOutbox).order_by(TelegramEventOutbox.created_at.asc()))
    ).scalars().all()

    by_entity = {(item.entity_id, item.recipient_user_id): item for item in events}

    assert (university_proposal.id, admin.id) in by_entity
    assert (university_proposal.id, moderator.id) not in by_entity

    assert (faculty_proposal.id, admin.id) in by_entity
    assert (faculty_proposal.id, moderator.id) in by_entity

    assert (subject_proposal.id, admin.id) in by_entity
    assert (subject_proposal.id, moderator.id) in by_entity

    assert by_entity[(faculty_proposal.id, admin.id)].payload["proposal_type"] == "faculty"
    assert by_entity[(subject_proposal.id, moderator.id)].payload["proposal_type"] == "subject"


@pytest.mark.asyncio
async def test_material_submit_creates_events_for_admins_and_scoped_moderators(session):
    university = await seed_university(session, "Material Event University")
    faculty = await seed_faculty(session, university.id, "Material Event Faculty")
    subject = await seed_subject(session, faculty.id, "Material Event Subject", 2)
    other_university = await seed_university(session, "Other Material Event University")
    other_faculty = await seed_faculty(session, other_university.id, "Other Material Event Faculty")
    other_subject = await seed_subject(session, other_faculty.id, "Other Material Event Subject", 2)

    admin = await seed_user(session, university.id, email="material-event-admin@example.com", role=UserRole.ADMIN)
    university_moderator = await seed_user(
        session,
        university.id,
        email="material-event-uni-mod@example.com",
        role=UserRole.MODERATOR,
    )
    faculty_moderator = await seed_user(
        session,
        university.id,
        email="material-event-fac-mod@example.com",
        role=UserRole.MODERATOR,
    )
    subject_moderator = await seed_user(
        session,
        university.id,
        email="material-event-sub-mod@example.com",
        role=UserRole.MODERATOR,
    )
    foreign_moderator = await seed_user(
        session,
        other_university.id,
        email="material-event-foreign-mod@example.com",
        role=UserRole.MODERATOR,
    )
    owner = await seed_user(session, university.id, email="material-event-owner@example.com")
    await add_university_scope(session, university_moderator.id, university.id)
    await add_faculty_scope(session, faculty_moderator.id, faculty.id)
    await add_subject_scope(session, subject_moderator.id, subject.id)
    await add_subject_scope(session, foreign_moderator.id, other_subject.id)

    material = await seed_material(session, owner, subject.id, "Reviewable Material")
    material.file_count = 1
    await session.commit()

    submitted = await MaterialService(session).submit(material.id, owner)

    events = (
        await session.execute(
            select(TelegramEventOutbox).where(
                TelegramEventOutbox.event_type == TelegramEventType.MATERIAL_SUBMITTED_FOR_REVIEW,
            )
        )
    ).scalars().all()
    recipients = {event.recipient_user_id for event in events}
    assert recipients == {
        admin.id,
        university_moderator.id,
        faculty_moderator.id,
        subject_moderator.id,
    }
    assert foreign_moderator.id not in recipients
    for event in events:
        assert event.entity_type == "material"
        assert event.entity_id != submitted.id
        assert event.payload["material_id"] == submitted.id
        assert event.payload["title"] == "Reviewable Material"
        assert event.payload["status"] == "pending_review"
        assert event.payload["frontend_url"] == (
            f"{get_settings().public_web_base_url.rstrip('/')}/materials/{submitted.slug}"
        )
        assert event.payload["university"] == {
            "id": university.id,
            "name": university.name,
            "slug": university.slug,
        }
        assert event.payload["faculty"] == {
            "id": faculty.id,
            "name": faculty.name,
            "slug": faculty.slug,
            "university_id": university.id,
        }
        assert event.payload["subject"] == {
            "id": subject.id,
            "name": subject.name,
            "slug": subject.slug,
            "semester": subject.semester,
            "faculty_id": faculty.id,
        }


@pytest.mark.asyncio
async def test_internal_material_moderation_endpoints_create_owner_events(client, session):
    university = await seed_university(session, "Internal Material Moderation University")
    faculty = await seed_faculty(session, university.id, "Internal Material Faculty")
    subject = await seed_subject(session, faculty.id, "Internal Material Subject", 1)
    owner = await seed_user(session, university.id, email="internal-material-owner@example.com")
    moderator = await seed_user(
        session,
        university.id,
        email="internal-material-mod@example.com",
        role=UserRole.MODERATOR,
    )
    await add_subject_scope(session, moderator.id, subject.id)
    session.add(
        TelegramLink(
            user_id=moderator.id,
            telegram_user_id=881122,
            telegram_username="materialmod",
            telegram_first_name="Material",
            linked_at=moderator.created_at,
        )
    )

    approve_target = await seed_material(session, owner, subject.id, "Approve From Telegram")
    reject_target = await seed_material(session, owner, subject.id, "Reject From Telegram")
    revision_target = await seed_material(session, owner, subject.id, "Revision From Telegram")
    for material in (approve_target, reject_target, revision_target):
        material.status = MaterialStatus.PENDING_REVIEW
        material.file_count = 1
    await session.commit()

    approve_payload = {"telegram_user_id": 881122}
    approve_path = f"/api/internal/v1/telegram/moderation/materials/{approve_target.id}/approve"
    approve_response = await client.post(
        approve_path,
        json=approve_payload,
        headers=internal_headers("POST", approve_path, approve_payload),
    )

    reject_payload = {
        "telegram_user_id": 881122,
        "reason": RejectReason.LOW_QUALITY.value,
        "note": "File quality is low",
    }
    reject_path = f"/api/internal/v1/telegram/moderation/materials/{reject_target.id}/reject"
    reject_response = await client.post(
        reject_path,
        json=reject_payload,
        headers=internal_headers("POST", reject_path, reject_payload),
    )

    revision_payload = {
        "telegram_user_id": 881122,
        "reason": RejectReason.UNREADABLE.value,
        "note": "Please upload a readable file",
    }
    revision_path = f"/api/internal/v1/telegram/moderation/materials/{revision_target.id}/request-revision"
    revision_response = await client.post(
        revision_path,
        json=revision_payload,
        headers=internal_headers("POST", revision_path, revision_payload),
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["material"]["id"] == approve_target.id
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert revision_response.status_code == 200
    assert revision_response.json()["status"] == "revision_requested"

    events = (
        await session.execute(
            select(TelegramEventOutbox).where(TelegramEventOutbox.recipient_user_id == owner.id)
        )
    ).scalars().all()
    by_type = {event.event_type: event for event in events}
    assert TelegramEventType.MATERIAL_APPROVED in by_type
    assert TelegramEventType.MATERIAL_REJECTED in by_type
    assert TelegramEventType.MATERIAL_REVISION_REQUESTED in by_type
    assert by_type[TelegramEventType.MATERIAL_APPROVED].payload["material_id"] == approve_target.id
    assert by_type[TelegramEventType.MATERIAL_APPROVED].payload["reviewed_by"]["user_id"] == moderator.id
    assert by_type[TelegramEventType.MATERIAL_REJECTED].payload["reason"] == RejectReason.LOW_QUALITY.value
    assert by_type[TelegramEventType.MATERIAL_REJECTED].payload["note"] == "File quality is low"
    assert by_type[TelegramEventType.MATERIAL_REVISION_REQUESTED].payload["reason"] == RejectReason.UNREADABLE.value
    assert by_type[TelegramEventType.MATERIAL_REVISION_REQUESTED].payload["note"] == "Please upload a readable file"


@pytest.mark.asyncio
async def test_internal_event_and_user_message_endpoints_return_pending_payloads(client, session):
    university = await seed_university(session, "Event API University")
    admin = await seed_user(session, university.id, email="event-api-admin@example.com", role=UserRole.ADMIN)
    linked_admin = TelegramLink(
        user_id=admin.id,
        telegram_user_id=777001,
        telegram_username="eventadmin",
        telegram_first_name="Event",
        linked_at=admin.created_at,
    )
    session.add(linked_admin)
    await session.commit()

    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Payload User",
            "email": "payload-user@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    assert registration.status_code == 201
    user_id = registration.json()["id"]

    user_message = await client.get(
        f"/api/internal/v1/telegram/notifications/users/{user_id}/telegram-message",
        headers=internal_headers(
            "GET",
            f"/api/internal/v1/telegram/notifications/users/{user_id}/telegram-message",
        ),
    )
    assert user_message.status_code == 200
    assert user_message.json()["user_id"] == user_id
    assert user_message.json()["university_name"] == university.name

    events_response = await client.get(
        "/api/internal/v1/telegram/events",
        headers=internal_headers("GET", "/api/internal/v1/telegram/events"),
    )
    assert events_response.status_code == 200
    body = events_response.json()
    assert body["total"] >= 1
    assert any(
        item["event_type"] == TelegramEventType.USER_REGISTERED.value
        and item["recipient"]["platform_user_id"] == admin.id
        and item["recipient"]["telegram_user_id"] == 777001
        for item in body["items"]
    )
