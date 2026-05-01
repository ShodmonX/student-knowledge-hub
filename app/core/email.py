from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException


class EmailDeliveryError(AppException):
    status_code = 502
    error_code = "email_delivery_failed"


class EmailService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        if not self.settings.mail_enabled:
            return False

        if self.settings.mail_api_token:
            await self._send_via_api(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
            return True

        message = EmailMessage()
        message["From"] = formataddr((self.settings.mail_from_name, self.settings.mail_from_email))
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        try:
            await asyncio.to_thread(self._send_message, message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Email yuborib bo'lmadi") from exc
        return True

    async def _send_via_api(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None,
    ) -> None:
        payload: dict[str, object] = {
            "from": {
                "email": self.settings.mail_from_email,
                "name": self.settings.mail_from_name,
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "text": text_body,
        }
        if html_body:
            payload["html"] = html_body

        try:
            async with httpx.AsyncClient(timeout=self.settings.mail_timeout_seconds) as client:
                response = await client.post(
                    self.settings.mail_api_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.mail_api_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Email yuborib bo'lmadi") from exc

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(
            self.settings.mail_host,
            self.settings.mail_port,
            timeout=self.settings.mail_timeout_seconds,
        ) as smtp:
            if self.settings.mail_starttls:
                smtp.starttls()
            if self.settings.mail_username and self.settings.mail_password:
                smtp.login(self.settings.mail_username, self.settings.mail_password)
            smtp.send_message(message)
