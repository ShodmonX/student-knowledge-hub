import asyncio
import signal

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.modules.telegram.dispatcher import TelegramEventDispatcher


async def run_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    print(
        "Telegram event worker started "
        f"(enabled={settings.telegram_event_push_enabled}, "
        f"base_url_configured={bool(settings.bot_internal_base_url)}, "
        f"poll_seconds={settings.telegram_event_poll_seconds}, "
        f"batch_size={settings.telegram_event_batch_size}, "
        f"max_attempts={settings.telegram_event_max_attempts})",
        flush=True,
    )
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                dispatcher = TelegramEventDispatcher(session)
                events = await dispatcher.events.list_pending_events(settings.telegram_event_batch_size)
                dispatched = await dispatcher.dispatch_events(events)
                await session.commit()
                if events:
                    failed = len(events) - dispatched
                    print(
                        "Telegram event dispatch cycle completed "
                        f"(picked={len(events)}, dispatched={dispatched}, failed={failed})",
                        flush=True,
                    )
        except Exception as e:
            print(f"Error dispatching Telegram events: {e}", flush=True)
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.telegram_event_poll_seconds,
            )
        except TimeoutError:
            continue


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)
    await run_worker(stop_event)


if __name__ == "__main__":
    asyncio.run(main())
