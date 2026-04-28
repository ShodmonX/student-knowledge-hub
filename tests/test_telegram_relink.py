import pytest

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
