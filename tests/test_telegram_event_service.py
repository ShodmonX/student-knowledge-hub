import pytest

from app.modules.telegram.enums import TelegramEventStatus, TelegramEventType
from app.modules.telegram.event_service import TelegramEventService
from tests.helpers import seed_university, seed_user


@pytest.mark.asyncio
async def test_telegram_event_service_creates_lists_and_updates_events(session):
    university = await seed_university(session, "Event University")
    recipient = await seed_user(session, university.id, email="event-admin@example.com")
    service = TelegramEventService(session)

    event = await service.create_event(
        event_type=TelegramEventType.PROPOSAL_CREATED,
        entity_type="proposal",
        entity_id="proposal-1",
        recipient=recipient,
        payload={"proposal_id": "proposal-1", "proposal_type": "faculty"},
    )
    await session.commit()

    pending = await service.list_pending_events()
    assert [item.id for item in pending] == [event.id]
    assert pending[0].status == TelegramEventStatus.PENDING
    assert pending[0].recipient_role == recipient.role.value

    duplicate = await service.create_event(
        event_type=TelegramEventType.PROPOSAL_CREATED,
        entity_type="proposal",
        entity_id="proposal-1",
        recipient=recipient,
        payload={"proposal_id": "proposal-1", "proposal_type": "faculty"},
    )
    assert duplicate.id == event.id

    await service.mark_failed(event, "temporary error")
    await session.commit()
    assert event.status == TelegramEventStatus.FAILED
    assert event.attempt_count == 1
    assert event.last_error == "temporary error"

    await service.mark_dispatched(event)
    await session.commit()
    assert event.status == TelegramEventStatus.DISPATCHED
    assert event.attempt_count == 2
    assert event.last_error is None
    assert event.dispatched_at is not None
