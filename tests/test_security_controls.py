from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core import security_controls
from app.core.cache import NullCacheBackend, RedisCacheBackend, get_cache
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, RateLimitExceeded
from app.core.security import create_access_token, create_refresh_token
from app.core.security_controls import (
    AccessTokenRevocationStore,
    AuthRateLimiter,
    SecurityKeyValueStore,
    clear_in_memory_security_store,
)


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int):
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, *keys: str):
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)

    async def incr(self, key: str):
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, ttl_seconds: int):
        self.expirations[key] = ttl_seconds

    async def ttl(self, key: str):
        return self.expirations.get(key, -1)


def _request(host: str = "127.0.0.1"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


@pytest.fixture(autouse=True)
async def reset_security_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "testing")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_in_memory_fallback", True)
    monkeypatch.setattr(settings, "access_token_revocation_enabled", True)
    monkeypatch.setattr(get_cache(), "backend", NullCacheBackend())
    await clear_in_memory_security_store()
    yield
    await clear_in_memory_security_store()


@pytest.mark.asyncio
async def test_security_store_uses_redis_backend_when_available(monkeypatch):
    fake_redis = FakeRedisClient()
    backend = RedisCacheBackend("redis://redis:6379/0")
    backend.client = fake_redis
    monkeypatch.setattr(get_cache(), "backend", backend)

    store = SecurityKeyValueStore()
    await store.set("token", "blocked", 30)
    assert await store.get("token") == "blocked"

    assert await store.increment("counter", 60) == 1
    assert await store.increment("counter", 60) == 2
    assert await store.ttl("counter") == 60

    await store.delete("token", "counter")
    assert await store.get("token") is None
    assert fake_redis.values == {}


@pytest.mark.asyncio
async def test_security_store_memory_expiry_and_unavailable_fallback(monkeypatch):
    now = 1_000.0
    monkeypatch.setattr(security_controls, "_now", lambda: now)

    store = SecurityKeyValueStore()
    await store.set("short", "value", 1)
    assert await store.get("short") == "value"

    now = 1_002.0
    assert await store.get("short") is None

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_in_memory_fallback", False)
    unavailable_store = SecurityKeyValueStore()
    assert unavailable_store.is_available() is False
    assert await unavailable_store.get("missing") is None
    await unavailable_store.set("ignored", "value", 30)
    assert await unavailable_store.increment("counter", 30) == 1
    assert await unavailable_store.ttl("counter") is None


@pytest.mark.asyncio
async def test_rate_limiter_disabled_and_unavailable_paths(monkeypatch):
    settings = get_settings()
    limiter = AuthRateLimiter()

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    await limiter.check("auth.test", "identity", 1, 60)
    await limiter.check_login_lockout(_request(), "user@example.com")
    await limiter.record_login_failure(_request(), "user@example.com")

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_in_memory_fallback", False)
    with pytest.raises(RateLimitExceeded) as exc_info:
        await AuthRateLimiter().check("auth.test", "identity", 1, 60)
    assert exc_info.value.message == "Rate limiting store is unavailable"


@pytest.mark.asyncio
async def test_rate_limiter_sensitive_wrappers_share_common_policy(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_sensitive_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_password_reset_confirm_max_requests", 1)
    limiter = AuthRateLimiter()
    request = _request("10.0.0.5")

    await limiter.check_password_reset_request_rate(request, "reset@example.com")
    await limiter.check_password_reset_confirm_rate(request, "token-one")
    with pytest.raises(RateLimitExceeded):
        await limiter.check_password_reset_confirm_rate(request, "token-one")

    await limiter.check_refresh_rate(request, "refresh-token-one")
    await limiter.check_sensitive_rate(request, "user-1", "auth.logout")
    with pytest.raises(RateLimitExceeded):
        await limiter.check_sensitive_rate(request, "user-1", "auth.logout")


@pytest.mark.asyncio
async def test_access_token_revocation_disabled_invalid_and_refresh_paths(monkeypatch):
    settings = get_settings()
    store = AccessTokenRevocationStore()

    monkeypatch.setattr(settings, "access_token_revocation_enabled", False)
    await store.revoke_token("not-a-token")
    await store.revoke_claims({"jti": "jti-1"})
    await store.ensure_not_revoked({})

    monkeypatch.setattr(settings, "access_token_revocation_enabled", True)
    await store.revoke_token("not-a-token")
    await store.revoke_token(create_refresh_token("user-1", "student"))


@pytest.mark.asyncio
async def test_access_token_revocation_unavailable_and_claim_validation(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_in_memory_fallback", False)
    revocations = AccessTokenRevocationStore()

    with pytest.raises(AuthenticationError, match="Token revocation store is unavailable"):
        await revocations.revoke_claims({"jti": "jti-1", "exp": datetime.now(UTC) + timedelta(minutes=5)})
    with pytest.raises(AuthenticationError, match="Token revocation store is unavailable"):
        await revocations.ensure_not_revoked({"jti": "jti-1"})

    monkeypatch.setattr(settings, "rate_limit_in_memory_fallback", True)
    await revocations.revoke_claims({"exp": datetime.now(UTC) + timedelta(minutes=5)})
    await revocations.revoke_claims({"jti": "expired", "exp": datetime.now(UTC) - timedelta(seconds=1)})

    with pytest.raises(AuthenticationError, match="Invalid access token"):
        await revocations.ensure_not_revoked({"exp": datetime.now(UTC) + timedelta(minutes=5)})


@pytest.mark.asyncio
async def test_access_token_revocation_marks_access_token_until_expiry():
    revocations = AccessTokenRevocationStore()
    token = create_access_token("user-1", "student")

    await revocations.revoke_token(token)

    with pytest.raises(AuthenticationError, match="Access token has been revoked"):
        await revocations.ensure_not_revoked(security_controls.decode_token(token))
