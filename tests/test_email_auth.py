from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.email import EmailDeliveryError, EmailService
from app.core.security import hash_password
from app.modules.auth.email_outbox import (
    EMAIL_STATUS_FAILED,
    EMAIL_STATUS_RETRY,
    EMAIL_STATUS_SENT,
    EmailOutboxService,
)
from app.modules.auth.models import EmailOutbox, EmailVerificationToken
from app.modules.auth.schemas import ResendVerificationRequest, VerifyEmailRequest
from app.modules.auth.service import AuthService
from app.modules.catalog.models import University
from app.modules.users.models import User
from app.utils.hashing import sha256_text
from app.utils.slug import slugify


async def _seed_university(session):
    university = University(name="Mailtrap University", slug=slugify("Mailtrap University"))
    session.add(university)
    await session.commit()
    await session.refresh(university)
    return university


async def _seed_user(session, university_id: str, email: str = "email-user@example.com"):
    user = User(
        full_name="Email User",
        email=email,
        hashed_password=hash_password("password123"),
        university_id=university_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _extract_token_from_email(message: EmailOutbox) -> str:
    for word in message.text_body.split():
        if "token=" in word:
            return parse_qs(urlparse(word).query)["token"][0]
    raise AssertionError("email token link not found")


@pytest.mark.asyncio
async def test_email_service_sends_via_configured_smtp(monkeypatch):
    smtp_calls: list[tuple[str, object]] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            smtp_calls.append(("connect", (host, port, timeout)))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def starttls(self):
            smtp_calls.append(("starttls", None))

        def login(self, username, password):
            smtp_calls.append(("login", (username, password)))

        def send_message(self, message):
            smtp_calls.append(("send", message))

    monkeypatch.setattr("app.core.email.smtplib.SMTP", FakeSMTP)
    settings = Settings(
        app_env="development",
        mail_enabled=True,
        mail_host="sandbox.smtp.mailtrap.io",
        mail_port=2525,
        mail_username="mailtrap-user",
        mail_password="mailtrap-password",
        mail_api_token=None,
        mail_from_email="no-reply@example.com",
        mail_from_name="Student Knowledge Hub",
    )

    sent = await EmailService(settings).send_email(
        to_email="student@example.com",
        subject="Verify email",
        text_body="Verify using the link",
        html_body="<p>Verify using the link</p>",
    )

    assert sent is True
    assert smtp_calls[0] == ("connect", ("sandbox.smtp.mailtrap.io", 2525, 10))
    assert ("starttls", None) in smtp_calls
    assert ("login", ("mailtrap-user", "mailtrap-password")) in smtp_calls
    send_call = [call for call in smtp_calls if call[0] == "send"][0]
    message = send_call[1]
    assert message["To"] == "student@example.com"
    assert message["Subject"] == "Verify email"


@pytest.mark.asyncio
async def test_email_service_sends_via_mailtrap_api(monkeypatch):
    requests: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, timeout):
            requests.append({"timeout": timeout})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, headers, json):
            requests.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("app.core.email.httpx.AsyncClient", FakeAsyncClient)
    settings = Settings(
        app_env="development",
        mail_enabled=True,
        mail_api_token="mailtrap-api-token",
        mail_from_email="no-reply@example.com",
        mail_from_name="Student Knowledge Hub",
    )

    sent = await EmailService(settings).send_email(
        to_email="student@example.com",
        subject="Verify email",
        text_body="Verify using the link",
        html_body="<p>Verify using the link</p>",
    )

    assert sent is True
    assert requests[1]["url"] == "https://send.api.mailtrap.io/api/send"
    assert requests[1]["headers"]["Authorization"] == "Bearer mailtrap-api-token"
    assert requests[1]["json"]["from"] == {
        "email": "no-reply@example.com",
        "name": "Student Knowledge Hub",
    }
    assert requests[1]["json"]["to"] == [{"email": "student@example.com"}]
    assert requests[1]["json"]["html"] == "<p>Verify using the link</p>"


@pytest.mark.asyncio
async def test_email_service_wraps_smtp_errors(monkeypatch):
    class BrokenSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            raise OSError("network down")

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("app.core.email.smtplib.SMTP", BrokenSMTP)
    settings = Settings(
        app_env="development",
        mail_enabled=True,
        mail_username="mailtrap-user",
        mail_password="mailtrap-password",
        mail_api_token=None,
        mail_from_email="no-reply@example.com",
    )

    with pytest.raises(EmailDeliveryError):
        await EmailService(settings).send_email(
            to_email="student@example.com",
            subject="Verify email",
            text_body="Verify using the link",
        )


@pytest.mark.asyncio
async def test_register_creates_email_verification_token(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_enabled", True)
    university = await _seed_university(session)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Email User",
            "email": "verify-create@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )

    assert response.status_code == 201
    user = await session.scalar(select(User).where(User.email == "verify-create@example.com"))
    token = await session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    assert token is not None
    assert token.consumed is False
    email = await session.scalar(
        select(EmailOutbox)
        .where(EmailOutbox.recipient_email == "verify-create@example.com")
        .order_by(EmailOutbox.created_at.desc())
    )
    assert email is not None
    raw_token = _extract_token_from_email(email)
    assert token.token == sha256_text(raw_token)
    assert token.token != raw_token


@pytest.mark.asyncio
async def test_verify_email_marks_user_verified(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_enabled", True)
    university = await _seed_university(session)
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Verify Me",
            "email": "verify-me@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    user = await session.scalar(select(User).where(User.email == "verify-me@example.com"))
    token = await session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    email = await session.scalar(
        select(EmailOutbox)
        .where(EmailOutbox.recipient_email == "verify-me@example.com")
        .order_by(EmailOutbox.created_at.desc())
    )
    assert email is not None
    raw_token = _extract_token_from_email(email)

    response = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 200
    assert response.json()["message"] == "Email tasdiqlandi"
    await session.refresh(user)
    await session.refresh(token)
    assert user.is_verified is True
    assert token.consumed is True


@pytest.mark.asyncio
async def test_verify_email_rejects_invalid_token(client):
    response = await client.post("/api/v1/auth/verify-email", json={"token": "x" * 64})

    assert response.status_code == 401
    assert response.json()["error_code"] == "unauthorized"


@pytest.mark.asyncio
async def test_resend_verification_rotates_unconsumed_token(client, session):
    university = await _seed_university(session)
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Resend Me",
            "email": "resend-me@example.com",
            "password": "password123",
            "university_id": university.id,
        },
    )
    user = await session.scalar(select(User).where(User.email == "resend-me@example.com"))
    first_token = await session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )

    response = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend-me@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == (
        "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."
    )
    await session.refresh(first_token)
    tokens = (
        await session.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user.id)
            .order_by(EmailVerificationToken.created_at.asc())
        )
    ).scalars().all()
    assert len(tokens) == 2
    assert tokens[0].consumed is True
    assert tokens[1].consumed is False


@pytest.mark.asyncio
async def test_auth_service_verify_and_resend_paths(session):
    university = await _seed_university(session)
    user = await _seed_user(session, university.id, "service-verify@example.com")
    service = AuthService(session)
    token = await service._create_email_verification_token(user)
    await session.commit()

    verified = await service.verify_email(VerifyEmailRequest(token=token))
    assert verified == {"message": "Email tasdiqlandi"}
    await session.refresh(user)
    assert user.is_verified is True

    verified_resend = await service.resend_verification(
        ResendVerificationRequest(email="service-verify@example.com")
    )
    assert verified_resend == {
        "message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."
    }
    missing_resend = await service.resend_verification(
        ResendVerificationRequest(email="missing-service@example.com")
    )
    assert missing_resend == {
        "message": "Agar akkaunt mavjud bo'lsa, email yuborish navbatga qo'yildi."
    }


@pytest.mark.asyncio
async def test_email_outbox_processes_sent_retry_and_failed_messages(session, monkeypatch):
    attempts: list[str] = []

    async def fake_send_email(self, to_email, subject, text_body, html_body=None):
        attempts.append(to_email)
        if to_email == "retry@example.com":
            raise EmailDeliveryError("temporary failure")
        if to_email == "failed@example.com":
            raise EmailDeliveryError("permanent failure")
        return True

    monkeypatch.setattr("app.modules.auth.email_outbox.EmailService.send_email", fake_send_email)
    settings = Settings(
        _env_file=None,
        app_env="testing",
        mail_enabled=True,
        email_outbox_batch_size=10,
        email_outbox_max_attempts=2,
        email_outbox_retry_base_seconds=30,
    )
    service = EmailOutboxService(session, settings)
    sent = await service.enqueue(
        recipient_email="sent@example.com",
        subject="Sent",
        text_body="sent",
    )
    retry = await service.enqueue(
        recipient_email="retry@example.com",
        subject="Retry",
        text_body="retry",
    )
    failed = await service.enqueue(
        recipient_email="failed@example.com",
        subject="Failed",
        text_body="failed",
    )
    assert sent is not None and retry is not None and failed is not None
    failed.attempt_count = 1
    await session.commit()

    result = await service.process_due()

    assert result == {"processed": 3, "sent": 1, "retry": 1, "failed": 1}
    assert attempts == ["sent@example.com", "retry@example.com", "failed@example.com"]
    await session.refresh(sent)
    await session.refresh(retry)
    await session.refresh(failed)
    assert sent.status == EMAIL_STATUS_SENT
    assert sent.sent_at is not None
    assert retry.status == EMAIL_STATUS_RETRY
    assert retry.next_attempt_at is not None
    assert failed.status == EMAIL_STATUS_FAILED
