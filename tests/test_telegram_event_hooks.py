import pytest
from sqlalchemy import select

from app.modules.catalog_proposals.schemas import FacultyProposalCreate, SubjectProposalCreate, UniversityProposalCreate
from app.modules.catalog_proposals.service import CatalogProposalService
from app.modules.telegram.enums import TelegramEventType
from app.modules.telegram.models import TelegramEventOutbox, TelegramLink
from app.modules.users.enums import UserRole
from tests.helpers import add_subject_scope, add_university_scope, internal_headers, seed_faculty, seed_subject, seed_university, seed_user


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
