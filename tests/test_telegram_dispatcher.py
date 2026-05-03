import pytest

from app.modules.telegram.dispatcher import TelegramEventDispatcher
from app.modules.telegram.enums import TelegramEventStatus, TelegramEventType
from app.modules.telegram.event_service import TelegramEventService
from tests.helpers import seed_university, seed_user


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    def __init__(self, *, status_code: int = 202, error: Exception | None = None, **_: object) -> None:
        self.status_code = status_code
        self.error = error
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict, headers: dict[str, str]):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error:
            raise self.error
        return _FakeResponse(self.status_code)


@pytest.mark.asyncio
async def test_dispatcher_marks_events_dispatched_on_success(session, monkeypatch):
    university = await seed_university(session, "Dispatch University")
    admin = await seed_user(session, university.id, email="dispatch-admin@example.com")
    service = TelegramEventService(session)
    event = await service.create_event(
        event_type=TelegramEventType.USER_REGISTERED,
        entity_type="user",
        entity_id="user-1",
        recipient=admin,
        payload={"user_id": "user-1"},
    )
    await session.commit()

    fake_client = _FakeAsyncClient(status_code=202)
    monkeypatch.setattr("app.modules.telegram.dispatcher.httpx.AsyncClient", lambda **kwargs: fake_client)

    dispatcher = TelegramEventDispatcher(session)
    monkeypatch.setattr(dispatcher.settings, "telegram_event_push_enabled", True)
    monkeypatch.setattr(dispatcher.settings, "bot_internal_base_url", "http://bot-service.local")
    monkeypatch.setattr(dispatcher.settings, "bot_internal_event_path", "/internal/events")
    monkeypatch.setattr(dispatcher.settings, "backend_service_name", "backend-api")
    monkeypatch.setattr(dispatcher.settings, "internal_auth_secret", "dispatch-secret")

    dispatched = await dispatcher.dispatch_pending_events()
    await session.commit()

    assert dispatched == 1
    assert event.status == TelegramEventStatus.DISPATCHED
    assert event.attempt_count == 1
    assert fake_client.calls[0]["url"] == "http://bot-service.local/internal/events"
    assert fake_client.calls[0]["json"]["event_type"] == TelegramEventType.USER_REGISTERED.value
    assert fake_client.calls[0]["headers"]["X-Internal-Service-Name"] == "backend-api"


@pytest.mark.asyncio
async def test_dispatcher_marks_events_failed_on_http_error(session, monkeypatch):
    university = await seed_university(session, "Dispatch Fail University")
    admin = await seed_user(session, university.id, email="dispatch-fail@example.com")
    service = TelegramEventService(session)
    event = await service.create_event(
        event_type=TelegramEventType.PROPOSAL_CREATED,
        entity_type="proposal",
        entity_id="proposal-1",
        recipient=admin,
        payload={"proposal_id": "proposal-1"},
    )
    await session.commit()

    fake_client = _FakeAsyncClient(status_code=500, text="failed")
    monkeypatch.setattr("app.modules.telegram.dispatcher.httpx.AsyncClient", lambda **kwargs: fake_client)

    dispatcher = TelegramEventDispatcher(session)
    monkeypatch.setattr(dispatcher.settings, "telegram_event_push_enabled", True)
    monkeypatch.setattr(dispatcher.settings, "bot_internal_base_url", "http://bot-service.local")
    monkeypatch.setattr(dispatcher.settings, "bot_internal_event_path", "/internal/events")
    monkeypatch.setattr(dispatcher.settings, "backend_service_name", "backend-api")
    monkeypatch.setattr(dispatcher.settings, "internal_auth_secret", "dispatch-secret")

    dispatched = await dispatcher.dispatch_pending_events()
    await session.commit()

    assert dispatched == 0
    assert event.status == TelegramEventStatus.FAILED
    assert event.attempt_count == 1
    assert event.last_error.startswith("500:")


@pytest.mark.asyncio
async def test_dispatcher_retries_failed_events_until_max_attempts(session, monkeypatch):
    university = await seed_university(session, "Dispatch Retry University")
    admin = await seed_user(session, university.id, email="dispatch-retry@example.com")
    service = TelegramEventService(session)
    retryable = await service.create_event(
        event_type=TelegramEventType.PASSWORD_RESET_REQUESTED,
        entity_type="user",
        entity_id="reset-token-1",
        recipient=admin,
        payload={"user_id": "user-1"},
    )
    retryable.status = TelegramEventStatus.FAILED
    retryable.attempt_count = 1
    exhausted = await service.create_event(
        event_type=TelegramEventType.PASSWORD_CHANGED,
        entity_type="user",
        entity_id="reset-token-1",
        recipient=admin,
        payload={"user_id": "user-1"},
    )
    exhausted.status = TelegramEventStatus.FAILED
    exhausted.attempt_count = 2
    await session.commit()

    fake_client = _FakeAsyncClient(status_code=202)
    monkeypatch.setattr("app.modules.telegram.dispatcher.httpx.AsyncClient", lambda **kwargs: fake_client)

    dispatcher = TelegramEventDispatcher(session)
    monkeypatch.setattr(dispatcher.settings, "telegram_event_push_enabled", True)
    monkeypatch.setattr(dispatcher.settings, "bot_internal_base_url", "http://bot-service.local")
    monkeypatch.setattr(dispatcher.settings, "bot_internal_event_path", "/internal/events")
    monkeypatch.setattr(dispatcher.settings, "backend_service_name", "backend-api")
    monkeypatch.setattr(dispatcher.settings, "internal_auth_secret", "dispatch-secret")
    monkeypatch.setattr(dispatcher.settings, "telegram_event_max_attempts", 2)

    dispatched = await dispatcher.dispatch_pending_events()
    await session.commit()

    assert dispatched == 1
    assert retryable.status == TelegramEventStatus.DISPATCHED
    assert retryable.attempt_count == 2
    assert exhausted.status == TelegramEventStatus.FAILED
    assert exhausted.attempt_count == 2
    assert len(fake_client.calls) == 1
