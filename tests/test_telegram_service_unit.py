import pytest

from app.modules.telegram.service import TelegramService


def test_build_deep_link_url_uses_configured_bot_username(session):
    service = TelegramService(session)
    original_username = service.settings.telegram_bot_username
    service.settings.telegram_bot_username = "test_bot"

    try:
        assert service.build_deep_link_url("abc123") == "https://t.me/test_bot?start=link_abc123"
    finally:
        service.settings.telegram_bot_username = original_username


def test_build_deep_link_url_requires_bot_username(session):
    service = TelegramService(session)
    original_username = service.settings.telegram_bot_username
    service.settings.telegram_bot_username = ""

    try:
        with pytest.raises(RuntimeError, match="TELEGRAM_BOT_USERNAME is not configured"):
            service.build_deep_link_url("abc123")
    finally:
        service.settings.telegram_bot_username = original_username
