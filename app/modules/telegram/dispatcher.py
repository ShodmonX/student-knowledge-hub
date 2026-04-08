from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.telegram.event_service import TelegramEventService
from app.modules.telegram.models import TelegramEventOutbox


class TelegramEventDispatcher:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.events = TelegramEventService(session)

    async def dispatch_events(self, events: list[TelegramEventOutbox]) -> int:
        if not self._is_enabled() or not events:
            return 0

        dispatched = 0
        timeout = httpx.Timeout(self.settings.telegram_bot_service_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for event in events:
                event_payload = await self.events.build_event_read(event)
                url = self._build_url()
                payload = event_payload.model_dump(mode="json")
                headers = self._build_headers("POST", self.settings.telegram_bot_service_event_path, payload)
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    if 200 <= response.status_code < 300:
                        await self.events.mark_dispatched(event)
                        dispatched += 1
                    else:
                        await self.events.mark_failed(event, f"{response.status_code}: {response.text[:200]}")
                except Exception as exc:  # pragma: no cover - exercised in tests via monkeypatch
                    await self.events.mark_failed(event, str(exc))
        return dispatched

    async def dispatch_pending_events(self, limit: int = 100) -> int:
        pending = await self.events.list_pending_events(limit)
        return await self.dispatch_events(pending)

    def _is_enabled(self) -> bool:
        return bool(
            self.settings.telegram_event_push_enabled
            and self.settings.telegram_bot_service_base_url
            and self.settings.telegram_bot_service_secret
        )

    def _build_url(self) -> str:
        return f"{self.settings.telegram_bot_service_base_url.rstrip('/')}{self.settings.telegram_bot_service_event_path}"

    def _build_headers(self, method: str, path: str, payload: dict) -> dict[str, str]:
        service_name = self.settings.telegram_bot_service_name
        secret = self.settings.telegram_bot_service_secret or ""
        timestamp = str(int(time.time()))
        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        body_hash = hashlib.sha256(raw_body).hexdigest()
        parsed = urlparse(path)
        canonical_path = parsed.path
        if parsed.query:
            canonical_path = f"{canonical_path}?{parsed.query}"
        canonical = "\n".join([service_name, timestamp, method.upper(), canonical_path, body_hash])
        signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "X-Internal-Service-Name": service_name,
            "X-Request-Timestamp": timestamp,
            "X-Signature": signature,
        }
