from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.telegram.models import TelegramLinkSession
from tests.helpers import access_headers, internal_headers, seed_university, seed_user


@pytest.mark.asyncio
async def test_relink_same_telegram_user_after_unlink_moves_existing_row(client, session):
    university = await seed_university(session, "Relink University")
    first_user = await seed_user(session, university.id, email="first-relink@example.com")
    second_user = await seed_user(session, university.id, email="second-relink@example.com")

    first_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(first_user))
    first_code = first_session.json()["manual_code"]
    first_verify_payload = {
        "code": first_code,
        "telegram_user": {
            "telegram_user_id": 6556314453,
            "username": "EnglishVocabularyAdmin",
            "first_name": "Admin",
        },
    }
    first_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", first_verify_payload),
        json=first_verify_payload,
    )
    assert first_verify.status_code == 200
    assert first_verify.json()["status"] == "linked_successfully"

    unlink = await client.delete("/api/v1/users/me/telegram-link", headers=access_headers(first_user))
    assert unlink.status_code == 200

    second_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(second_user))
    second_code = second_session.json()["manual_code"]
    second_verify_payload = {
        "code": second_code,
        "telegram_user": {
            "telegram_user_id": 6556314453,
            "username": "EnglishVocabularyAdmin",
            "first_name": "Admin",
        },
    }
    second_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", second_verify_payload),
        json=second_verify_payload,
    )
    assert second_verify.status_code == 200
    assert second_verify.json()["status"] == "linked_successfully"

    identity = await client.get(
        "/api/internal/v1/telegram/users/6556314453/identity",
        headers=internal_headers("GET", "/api/internal/v1/telegram/users/6556314453/identity"),
    )
    assert identity.status_code == 200
    assert identity.json()["platform_user"]["id"] == second_user.id


@pytest.mark.asyncio
async def test_relink_same_platform_user_to_new_telegram_after_unlink_reuses_existing_row(client, session):
    university = await seed_university(session, "Platform Relink University")
    user = await seed_user(session, university.id, email="platform-relink-2@example.com")

    first_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(user))
    first_code = first_session.json()["manual_code"]
    first_verify_payload = {
        "code": first_code,
        "telegram_user": {
            "telegram_user_id": 1111,
            "username": "first_account",
            "first_name": "First",
        },
    }
    first_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", first_verify_payload),
        json=first_verify_payload,
    )
    assert first_verify.status_code == 200
    assert first_verify.json()["status"] == "linked_successfully"

    unlink = await client.delete("/api/v1/users/me/telegram-link", headers=access_headers(user))
    assert unlink.status_code == 200

    second_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(user))
    second_code = second_session.json()["manual_code"]
    second_verify_payload = {
        "code": second_code,
        "telegram_user": {
            "telegram_user_id": 2222,
            "username": "second_account",
            "first_name": "Second",
        },
    }
    second_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", second_verify_payload),
        json=second_verify_payload,
    )
    assert second_verify.status_code == 200
    assert second_verify.json()["status"] == "linked_successfully"

    identity = await client.get(
        "/api/internal/v1/telegram/users/2222/identity",
        headers=internal_headers("GET", "/api/internal/v1/telegram/users/2222/identity"),
    )
    assert identity.status_code == 200
    assert identity.json()["platform_user"]["id"] == user.id


@pytest.mark.asyncio
async def test_active_telegram_link_conflicts_are_rejected(client, session):
    university = await seed_university(session, "Telegram Conflict University")
    first_user = await seed_user(session, university.id, email="telegram-conflict-first@example.com")
    second_user = await seed_user(session, university.id, email="telegram-conflict-second@example.com")

    first_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(first_user))
    first_code = first_session.json()["manual_code"]
    first_payload = {
        "code": first_code,
        "telegram_user": {
            "telegram_user_id": 3001,
            "username": "conflict_first",
            "first_name": "Conflict",
        },
    }
    first_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", first_payload),
        json=first_payload,
    )
    assert first_verify.status_code == 200
    assert first_verify.json()["status"] == "linked_successfully"

    same_user_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(first_user))
    same_user_code = same_user_session.json()["manual_code"]
    same_user_payload = {
        "code": same_user_code,
        "telegram_user": {
            "telegram_user_id": 3001,
            "username": "conflict_first",
            "first_name": "Conflict",
        },
    }
    same_user_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", same_user_payload),
        json=same_user_payload,
    )
    assert same_user_verify.status_code == 200
    assert same_user_verify.json()["status"] == "already_linked_to_this_account"

    new_telegram_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(first_user))
    new_telegram_code = new_telegram_session.json()["manual_code"]
    new_telegram_payload = {
        "code": new_telegram_code,
        "telegram_user": {
            "telegram_user_id": 3002,
            "username": "conflict_second",
            "first_name": "Second",
        },
    }
    new_telegram_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", new_telegram_payload),
        json=new_telegram_payload,
    )
    assert new_telegram_verify.status_code == 200
    assert new_telegram_verify.json()["status"] == "platform_account_has_another_telegram"

    second_user_session = await client.post("/api/v1/users/me/telegram-link-sessions", headers=access_headers(second_user))
    second_user_code = second_user_session.json()["manual_code"]
    second_user_payload = {
        "code": second_user_code,
        "telegram_user": {
            "telegram_user_id": 3001,
            "username": "conflict_first",
            "first_name": "Conflict",
        },
    }
    second_user_verify = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", second_user_payload),
        json=second_user_payload,
    )
    assert second_user_verify.status_code == 200
    assert second_user_verify.json()["status"] == "telegram_account_already_used"


@pytest.mark.asyncio
async def test_invalid_expired_and_missing_telegram_link_paths(client, session):
    university = await seed_university(session, "Telegram Invalid Path University")
    user = await seed_user(session, university.id, email="telegram-invalid-path@example.com")

    status_response = await client.get("/api/v1/users/me/telegram-link", headers=access_headers(user))
    assert status_response.status_code == 200
    assert status_response.json() == {
        "is_linked": False,
        "telegram_username": None,
        "telegram_first_name": None,
        "linked_at": None,
    }

    missing_unlink = await client.delete("/api/v1/users/me/telegram-link", headers=access_headers(user))
    assert missing_unlink.status_code == 404

    invalid_code_payload = {
        "code": "TG-000000",
        "telegram_user": {"telegram_user_id": 4100},
    }
    invalid_code = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", invalid_code_payload),
        json=invalid_code_payload,
    )
    assert invalid_code.status_code == 200
    assert invalid_code.json()["status"] == "invalid_code"

    invalid_token_payload = {
        "token": "invalid-token-value",
        "telegram_user": {"telegram_user_id": 4100},
    }
    invalid_token = await client.post(
        "/api/internal/v1/telegram/link/consume",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/consume", invalid_token_payload),
        json=invalid_token_payload,
    )
    assert invalid_token.status_code == 200
    assert invalid_token.json()["status"] == "token_invalid"

    link_session_response = await client.post(
        "/api/v1/users/me/telegram-link-sessions",
        headers=access_headers(user),
    )
    manual_code = link_session_response.json()["manual_code"]
    db_session = await session.scalar(
        select(TelegramLinkSession).where(TelegramLinkSession.user_id == user.id)
    )
    db_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    expired_payload = {
        "code": manual_code,
        "telegram_user": {"telegram_user_id": 4101},
    }
    expired_response = await client.post(
        "/api/internal/v1/telegram/link/verify-code",
        headers=internal_headers("POST", "/api/internal/v1/telegram/link/verify-code", expired_payload),
        json=expired_payload,
    )
    assert expired_response.status_code == 200
    assert expired_response.json()["status"] == "expired_code"
