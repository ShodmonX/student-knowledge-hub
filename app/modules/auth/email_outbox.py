from __future__ import annotations

from datetime import UTC, datetime, timedelta

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.email import EmailDeliveryError, EmailService
from app.modules.auth.models import EmailOutbox

logger = logging.getLogger(__name__)

EMAIL_STATUS_PENDING = "pending"
EMAIL_STATUS_RETRY = "retry"
EMAIL_STATUS_SENT = "sent"
EMAIL_STATUS_FAILED = "failed"


class EmailOutboxService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.email = EmailService(self.settings)

    async def enqueue(
        self,
        *,
        recipient_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailOutbox | None:
        if not self.settings.mail_enabled:
            return None
        message = EmailOutbox(
            recipient_email=recipient_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            max_attempts=self.settings.email_outbox_max_attempts,
            next_attempt_at=datetime.now(UTC),
        )
        self.session.add(message)
        return message

    async def process_due(self, limit: int | None = None) -> dict[str, int]:
        now = datetime.now(UTC)
        batch_size = limit or self.settings.email_outbox_batch_size
        result = await self.session.execute(
            select(EmailOutbox)
            .where(
                EmailOutbox.status.in_([EMAIL_STATUS_PENDING, EMAIL_STATUS_RETRY]),
                EmailOutbox.attempt_count < EmailOutbox.max_attempts,
                EmailOutbox.next_attempt_at <= now,
            )
            .order_by(EmailOutbox.next_attempt_at.asc(), EmailOutbox.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        messages = list(result.scalars().all())
        sent = 0
        failed = 0
        retried = 0
        for message in messages:
            try:
                await self._send_one(message)
                sent += 1
            except EmailDeliveryError:
                if message.status == EMAIL_STATUS_FAILED:
                    failed += 1
                else:
                    retried += 1
        await self.session.commit()
        return {
            "processed": len(messages),
            "sent": sent,
            "retry": retried,
            "failed": failed,
        }

    async def _send_one(self, message: EmailOutbox) -> None:
        message.attempt_count += 1
        message.last_attempt_at = datetime.now(UTC)
        try:
            await self.email.send_email(
                to_email=message.recipient_email,
                subject=message.subject,
                text_body=message.text_body,
                html_body=message.html_body,
            )
            logger.info(
                f"Email successfully sent to {message.recipient_email} (subject: {message.subject})"
            )
        except Exception as exc:
            message.last_error = str(exc)
            if message.attempt_count >= message.max_attempts:
                message.status = EMAIL_STATUS_FAILED
                logger.error(
                    f"Email failed permanently to {message.recipient_email} "
                    f"after {message.attempt_count} attempts. Error: {exc}"
                )
            else:
                message.status = EMAIL_STATUS_RETRY
                delay = self.settings.email_outbox_retry_base_seconds * (
                    2 ** max(message.attempt_count - 1, 0)
                )
                message.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                logger.warning(
                    f"Email failed to {message.recipient_email}, retrying in {delay}s. "
                    f"Attempt {message.attempt_count}/{message.max_attempts}. Error: {exc}"
                )
            raise EmailDeliveryError("Email jo'natishda kutilmagan xatolik yuz berdi") from exc
        message.status = EMAIL_STATUS_SENT
        message.sent_at = datetime.now(UTC)
        message.last_error = None
