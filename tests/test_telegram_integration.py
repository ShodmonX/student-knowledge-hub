from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.catalog_proposals.models import FacultyProposal, SubjectProposal, UniversityProposal
from app.modules.telegram.models import TelegramLink, TelegramLinkSession
from app.modules.users.enums import UserRole
from app.utils.hashing import sha256_text
from tests.helpers import (
    access_headers,
    add_university_scope,
    internal_headers,
    seed_faculty,
    seed_subject,
    seed_university,
    seed_user,
)


@pytest.mark.asyncio
async def test_public_linking_flow_and_internal_consume(client, session):
    university = await seed_university(session)
    user = await seed_user(session, university.id, email="telegram-user@example.com")

    create_response = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(user))
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["deep_link_url"].startswith("https://t.me/bilimhub_bot?start=link_")
    token = payload["deep_link_url"].split("link_", 1)[1]

    consume_response = await client.post(
        "/api/internal/v1/telegram/link/consume",
        headers=internal_headers(
            "POST",
            "/api/internal/v1/telegram/link/consume",
            {
                "token": token,
                "telegram_user": {
                    "telegram_user_id": 123456789,
                    "username": "shodmonx",
                    "first_name": "Shodmon",
                    "last_name": "Xolmurodov",
                    "language_code": "uz",
                },
            },
        ),
        json={
            "token": token,
            "telegram_user": {
                "telegram_user_id": 123456789,
                "username": "shodmonx",
                "first_name": "Shodmon",
                "last_name": "Xolmurodov",
                "language_code": "uz",
            },
        },
    )
    assert consume_response.status_code == 200
    assert consume_response.json()["status"] == "linked_successfully"

    status_response = await client.get("/api/v1/users/me/telegram-link", headers=access_headers(user))
    assert status_response.status_code == 200
    assert status_response.json()["is_linked"] is True
    assert status_response.json()["telegram_username"] == "shodmonx"

    unlink_response = await client.delete("/api/v1/users/me/telegram-link", headers=access_headers(user))
    assert unlink_response.status_code == 200
    assert unlink_response.json() == {"status": "unlinked"}

    identity_response = await client.get(
        "/api/internal/v1/telegram/users/123456789/identity",
        headers=internal_headers("GET", "/api/internal/v1/telegram/users/123456789/identity"),
    )
    assert identity_response.status_code == 200
    assert identity_response.json() == {"is_linked": False, "platform_user": None}


@pytest.mark.asyncio
async def test_manual_code_verify_identity_and_invalid_internal_token(client, session):
    university = await seed_university(session, "Code University")
    user = await seed_user(session, university.id, email="code-user@example.com")

    session_response = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(user))
    code = session_response.json()["manual_code"]

    unauthorized_response = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        json={"code": code, "telegram_user": {"telegram_user_id": 1001}},
    )
    assert unauthorized_response.status_code == 401

    verify_response = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers(
            "POST",
            "/api/internal/v1/telegram/link/verify-code",
            {
                "code": code,
                "telegram_user": {
                    "telegram_user_id": 1001,
                    "username": "codeuser",
                    "first_name": "Code",
                },
            },
        ),
        json={
            "code": code,
            "telegram_user": {
                "telegram_user_id": 1001,
                "username": "codeuser",
                "first_name": "Code",
            },
        },
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "linked_successfully"

    second_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers(
            "POST",
            "/api/internal/v1/telegram/link/verify-code",
            {"code": code, "telegram_user": {"telegram_user_id": 1001}},
        ),
        json={"code": code, "telegram_user": {"telegram_user_id": 1001}},
    )
    assert second_verify.status_code == 200
    assert second_verify.json()["status"] == "used_code"

    identity_response = await client.get(
        "/api/internal/v1/telegram/users/1001/identity",
        headers=internal_headers("GET", "/api/internal/v1/telegram/users/1001/identity"),
    )
    assert identity_response.status_code == 200
    assert identity_response.json()["is_linked"] is True
    assert identity_response.json()["platform_user"]["id"] == user.id
    assert identity_response.json()["platform_user"]["role"] == UserRole.STUDENT.value


@pytest.mark.asyncio
async def test_internal_proposal_endpoints_cover_detail_list_message_and_moderation(client, session):
    university = await seed_university(session, "Moderation University")
    moderator = await seed_user(
        session,
        university.id,
        email="moderator@example.com",
        role=UserRole.MODERATOR,
        full_name="Moderator User",
    )
    admin = await seed_user(
        session,
        university.id,
        email="telegram-admin@example.com",
        role=UserRole.ADMIN,
        full_name="Admin User",
    )
    submitter = await seed_user(session, university.id, email="submitter@example.com", full_name="Submitter User")
    await add_university_scope(session, moderator.id, university.id)

    faculty = await seed_faculty(session, university.id, "Engineering")
    subject = await seed_subject(session, faculty.id, "Physics", semester=2)

    faculty_proposal = FacultyProposal(
        university_id=university.id,
        proposed_name="Applied Math",
        proposed_slug="applied-math",
        proposed_description="New faculty proposal",
        created_by=submitter.id,
    )
    subject_proposal = SubjectProposal(
        faculty_id=faculty.id,
        proposed_name="Quantum Basics",
        proposed_slug="quantum-basics",
        proposed_code="QB-101",
        proposed_semester=2,
        proposed_description="New subject proposal",
        created_by=submitter.id,
    )
    university_proposal = UniversityProposal(
        proposed_name="Second Campus",
        proposed_slug="second-campus",
        proposed_description="New university proposal",
        created_by=submitter.id,
    )
    session.add_all([faculty_proposal, subject_proposal, university_proposal])
    session.add_all(
        [
            TelegramLink(
                user_id=moderator.id,
                telegram_user_id=2222,
                telegram_username="moduser",
                telegram_first_name="Mod",
                linked_at=datetime.now(UTC),
            ),
            TelegramLink(
                user_id=admin.id,
                telegram_user_id=3333,
                telegram_username="adminuser",
                telegram_first_name="Admin",
                linked_at=datetime.now(UTC),
            ),
        ]
    )
    await session.commit()

    detail_response = await client.get(
        f"/api/internal/v1/telegram/moderation/proposals/{faculty_proposal.id}",
        headers=internal_headers(
            "GET",
            f"/api/internal/v1/telegram/moderation/proposals/{faculty_proposal.id}",
        ),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["proposal_type"] == "faculty"
    assert detail_response.json()["scope"]["university_id"] == university.id

    list_response = await client.get(
        "/api/internal/v1/telegram/moderation/proposals",
        headers=internal_headers(
            "GET",
            "/api/internal/v1/telegram/moderation/proposals?proposal_type=faculty&limit=10&offset=0",
        ),
        params={"proposal_type": "faculty", "limit": 10, "offset": 0},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == faculty_proposal.id

    payload_response = await client.get(
        f"/api/internal/v1/telegram/notifications/proposals/{faculty_proposal.id}/telegram-message",
        headers=internal_headers(
            "GET",
            f"/api/internal/v1/telegram/notifications/proposals/{faculty_proposal.id}/telegram-message",
        ),
    )
    assert payload_response.status_code == 200
    assert payload_response.json()["approve_callback_data"] == f"proposal:approve:{faculty_proposal.id}"

    approve_response = await client.post(
        f"/api/internal/v1/telegram/moderation/proposals/{faculty_proposal.id}/approve",
        headers=internal_headers(
            "POST",
            f"/api/internal/v1/telegram/moderation/proposals/{faculty_proposal.id}/approve",
            {"telegram_user_id": 2222},
        ),
        json={"telegram_user_id": 2222},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    reject_response = await client.post(
        f"/api/internal/v1/telegram/moderation/proposals/{subject_proposal.id}/reject",
        headers=internal_headers(
            "POST",
            f"/api/internal/v1/telegram/moderation/proposals/{subject_proposal.id}/reject",
            {"telegram_user_id": 2222, "reason": "Duplicate subject proposal"},
        ),
        json={"telegram_user_id": 2222, "reason": "Duplicate subject proposal"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    forbidden_response = await client.post(
        f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
        headers=internal_headers(
            "POST",
            f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
            {"telegram_user_id": 2222},
        ),
        json={"telegram_user_id": 2222},
    )
    assert forbidden_response.status_code == 200
    assert forbidden_response.json()["status"] == "forbidden"

    admin_approve = await client.post(
        f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
        headers=internal_headers(
            "POST",
            f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
            {"telegram_user_id": 3333},
        ),
        json={"telegram_user_id": 3333},
    )
    assert admin_approve.status_code == 200
    assert admin_approve.json()["status"] == "approved"

    duplicate_admin_approve = await client.post(
        f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
        headers=internal_headers(
            "POST",
            f"/api/internal/v1/telegram/moderation/proposals/{university_proposal.id}/approve",
            {"telegram_user_id": 3333},
        ),
        json={"telegram_user_id": 3333},
    )
    assert duplicate_admin_approve.status_code == 200
    assert duplicate_admin_approve.json()["status"] == "already_processed"


@pytest.mark.asyncio
async def test_expired_and_conflicting_link_sessions_return_expected_business_statuses(client, session):
    university = await seed_university(session, "Conflict University")
    primary_user = await seed_user(session, university.id, email="primary@example.com")
    second_user = await seed_user(session, university.id, email="secondary@example.com")

    first_session = TelegramLinkSession(
        user_id=primary_user.id,
        token_hash="token-hash-1",
        code_hash="code-hash-1",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    second_session = TelegramLinkSession(
        user_id=second_user.id,
        token_hash="token-hash-2",
        code_hash="code-hash-2",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    existing_link = TelegramLink(
        user_id=primary_user.id,
        telegram_user_id=8888,
        telegram_username="occupied",
        telegram_first_name="Occupied",
        linked_at=datetime.now(UTC),
    )
    session.add_all([first_session, second_session, existing_link])
    await session.commit()

    expired_session = await session.scalar(
        select(TelegramLinkSession).where(TelegramLinkSession.id == first_session.id)
    )
    expired_session.token_hash = sha256_text("expired-token")
    conflict_session = await session.scalar(
        select(TelegramLinkSession).where(TelegramLinkSession.id == second_session.id)
    )
    conflict_session.token_hash = sha256_text("conflict-token")
    await session.commit()

    expired_response = await client.post(
        "/api/internal/v1/telegram/link/consume",
        headers=internal_headers(
            "POST",
            "/api/internal/v1/telegram/link/consume",
            {"token": "expired-token", "telegram_user": {"telegram_user_id": 7777}},
        ),
        json={"token": "expired-token", "telegram_user": {"telegram_user_id": 7777}},
    )
    assert expired_response.status_code == 200
    assert expired_response.json()["status"] == "token_expired"

    conflict_response = await client.post(
        "/api/internal/v1/telegram/link/consume",
        headers=internal_headers(
            "POST",
            "/api/internal/v1/telegram/link/consume",
            {"token": "conflict-token", "telegram_user": {"telegram_user_id": 8888}},
        ),
        json={"token": "conflict-token", "telegram_user": {"telegram_user_id": 8888}},
    )
    assert conflict_response.status_code == 200
    assert conflict_response.json()["status"] == "telegram_account_already_used"
