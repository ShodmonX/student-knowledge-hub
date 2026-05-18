import asyncio
import signal
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.auth.email_outbox import EmailOutboxService

logger = logging.getLogger(__name__)


async def run_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    logger.info("Email worker started")
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                result = await EmailOutboxService(session, settings).process_due()
                if result["processed"] > 0:
                    logger.info(f"Processed batch: {result}")
        except Exception as e:
            # Faylni xatoliklar qulab tushishidan saqlash
            logger.exception(f"Error processing email outbox: {e}")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.email_outbox_poll_seconds,
            )
        except TimeoutError:
            continue


async def main() -> None:
    configure_logging()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)
    await run_worker(stop_event)


if __name__ == "__main__":
    asyncio.run(main())
