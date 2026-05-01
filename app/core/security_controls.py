from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from app.core.cache import RedisCacheBackend, get_cache
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, RateLimitExceeded
from app.core.security import claims_expiration_to_datetime, decode_token

_memory_lock = asyncio.Lock()
_memory_store: dict[str, tuple[str, float | None]] = {}


def _now() -> float:
    return time.time()


async def clear_in_memory_security_store() -> None:
    async with _memory_lock:
        _memory_store.clear()


class SecurityKeyValueStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def key_prefix(self) -> str:
        return self.settings.rate_limit_key_prefix.strip(":") or "skh"

    def namespaced(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def _redis_client(self):
        backend = get_cache().backend
        if isinstance(backend, RedisCacheBackend) and backend.client is not None:
            return backend.client
        return None

    def _allow_memory_fallback(self) -> bool:
        return self.settings.rate_limit_in_memory_fallback and not self.settings.is_production

    def is_available(self) -> bool:
        return self._redis_client() is not None or self._allow_memory_fallback()

    async def get(self, key: str) -> str | None:
        key = self.namespaced(key)
        client = self._redis_client()
        if client is not None:
            return await client.get(key)
        if not self._allow_memory_fallback():
            return None
        async with _memory_lock:
            self._delete_if_expired_locked(key)
            value = _memory_store.get(key)
            return value[0] if value else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        key = self.namespaced(key)
        ttl_seconds = max(int(ttl_seconds), 1)
        client = self._redis_client()
        if client is not None:
            await client.set(key, value, ex=ttl_seconds)
            return
        if not self._allow_memory_fallback():
            return
        async with _memory_lock:
            _memory_store[key] = (value, _now() + ttl_seconds)

    async def delete(self, *keys: str) -> None:
        namespaced = [self.namespaced(key) for key in keys]
        client = self._redis_client()
        if client is not None:
            if namespaced:
                await client.delete(*namespaced)
            return
        if not self._allow_memory_fallback():
            return
        async with _memory_lock:
            for key in namespaced:
                _memory_store.pop(key, None)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        key = self.namespaced(key)
        ttl_seconds = max(int(ttl_seconds), 1)
        client = self._redis_client()
        if client is not None:
            value = await client.incr(key)
            if value == 1:
                await client.expire(key, ttl_seconds)
            return int(value)
        if not self._allow_memory_fallback():
            return 1
        async with _memory_lock:
            self._delete_if_expired_locked(key)
            stored_value, expires_at = _memory_store.get(key, ("0", None))
            value = int(stored_value) + 1
            _memory_store[key] = (str(value), expires_at or (_now() + ttl_seconds))
            return value

    async def ttl(self, key: str) -> int | None:
        key = self.namespaced(key)
        client = self._redis_client()
        if client is not None:
            ttl = await client.ttl(key)
            return int(ttl) if ttl and ttl > 0 else None
        if not self._allow_memory_fallback():
            return None
        async with _memory_lock:
            self._delete_if_expired_locked(key)
            value = _memory_store.get(key)
            if not value or value[1] is None:
                return None
            return max(int(value[1] - _now()), 1)

    @staticmethod
    def _delete_if_expired_locked(key: str) -> None:
        value = _memory_store.get(key)
        if value and value[1] is not None and value[1] <= _now():
            _memory_store.pop(key, None)


def client_identity(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def hash_identity(*parts: Any) -> str:
    raw = "|".join(str(part).strip().lower() for part in parts if part is not None)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuthRateLimiter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = SecurityKeyValueStore()

    async def check(
        self,
        scope: str,
        identity: str,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        if not self.settings.rate_limit_enabled:
            return
        if not self.store.is_available():
            raise RateLimitExceeded("Rate limiting store is unavailable")
        key = f"rl:{scope}:{hash_identity(identity)}"
        count = await self.store.increment(key, window_seconds)
        if count > max_requests:
            retry_after = await self.store.ttl(key)
            raise RateLimitExceeded(
                "Too many requests",
                details={
                    "scope": scope,
                    "retry_after_seconds": retry_after or window_seconds,
                },
            )

    async def check_login_lockout(self, request: Request, email: str) -> None:
        if not self.settings.rate_limit_enabled:
            return
        lock_key = self._login_lock_key(request, email)
        if await self.store.get(lock_key):
            retry_after = await self.store.ttl(lock_key)
            raise RateLimitExceeded(
                "Too many failed login attempts",
                details={
                    "scope": "auth.login.lockout",
                    "retry_after_seconds": retry_after or self.settings.login_lockout_seconds,
                },
            )

    async def record_login_failure(self, request: Request, email: str) -> None:
        if not self.settings.rate_limit_enabled:
            return
        fail_key = self._login_fail_key(request, email)
        attempts = await self.store.increment(fail_key, self.settings.login_lockout_window_seconds)
        if attempts >= self.settings.login_lockout_max_attempts:
            lock_key = self._login_lock_key(request, email)
            await self.store.set(lock_key, "1", self.settings.login_lockout_seconds)
            raise RateLimitExceeded(
                "Too many failed login attempts",
                details={
                    "scope": "auth.login.lockout",
                    "retry_after_seconds": self.settings.login_lockout_seconds,
                },
            )

    async def record_login_success(self, request: Request, email: str) -> None:
        await self.store.delete(
            self._login_fail_key(request, email),
            self._login_lock_key(request, email),
        )

    async def check_login_rate(self, request: Request, email: str) -> None:
        await self.check(
            "auth.login",
            hash_identity(client_identity(request), email),
            self.settings.rate_limit_login_max_requests,
            self.settings.rate_limit_login_window_seconds,
        )

    async def check_register_rate(self, request: Request, email: str) -> None:
        await self.check(
            "auth.register",
            hash_identity(client_identity(request), email),
            self.settings.rate_limit_register_max_requests,
            self.settings.rate_limit_register_window_seconds,
        )

    async def check_password_reset_request_rate(self, request: Request, email: str) -> None:
        await self.check(
            "auth.password_reset.request",
            hash_identity(client_identity(request), email),
            self.settings.rate_limit_password_reset_request_max_requests,
            self.settings.rate_limit_password_reset_request_window_seconds,
        )

    async def check_password_reset_confirm_rate(self, request: Request, token: str) -> None:
        await self.check(
            "auth.password_reset.confirm",
            hash_identity(client_identity(request), token),
            self.settings.rate_limit_password_reset_confirm_max_requests,
            self.settings.rate_limit_password_reset_confirm_window_seconds,
        )

    async def check_refresh_rate(self, request: Request, refresh_token: str) -> None:
        await self.check(
            "auth.refresh",
            hash_identity(client_identity(request), refresh_token),
            self.settings.rate_limit_refresh_max_requests,
            self.settings.rate_limit_refresh_window_seconds,
        )

    async def check_sensitive_rate(self, request: Request, identity: str, scope: str) -> None:
        await self.check(
            scope,
            hash_identity(client_identity(request), identity),
            self.settings.rate_limit_sensitive_max_requests,
            self.settings.rate_limit_sensitive_window_seconds,
        )

    def _login_fail_key(self, request: Request, email: str) -> str:
        return f"bf:login:fail:{hash_identity(client_identity(request), email)}"

    def _login_lock_key(self, request: Request, email: str) -> str:
        return f"bf:login:lock:{hash_identity(client_identity(request), email)}"


class AccessTokenRevocationStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = SecurityKeyValueStore()

    async def revoke_token(self, token: str) -> None:
        if not self.settings.access_token_revocation_enabled:
            return
        try:
            claims = decode_token(token)
        except AuthenticationError:
            return
        if claims.get("type") != "access":
            return
        await self.revoke_claims(claims)

    async def revoke_claims(self, claims: dict[str, Any]) -> None:
        if not self.settings.access_token_revocation_enabled:
            return
        if not self.store.is_available():
            raise AuthenticationError("Token revocation store is unavailable")
        jti = claims.get("jti")
        if not jti:
            return
        expires_at = claims_expiration_to_datetime(claims)
        ttl_seconds = int((expires_at - datetime.now(UTC)).total_seconds())
        if ttl_seconds <= 0:
            return
        await self.store.set(self._key(jti), "1", ttl_seconds)

    async def revoke_all_for_user(self, user_id: str) -> None:
        if not self.settings.access_token_revocation_enabled:
            return
        if not self.store.is_available():
            raise AuthenticationError("Token revocation store is unavailable")
        now_ts = int(datetime.now(UTC).timestamp())
        # Cache expiration based on access token expiration time
        ttl = self.settings.access_token_expire_minutes * 60
        await self.store.set(f"auth:revoked_all_access:{user_id}", str(now_ts), ttl)

    async def ensure_not_revoked(self, claims: dict[str, Any]) -> None:
        if not self.settings.access_token_revocation_enabled:
            return
        if not self.store.is_available():
            raise AuthenticationError("Token revocation store is unavailable")
        jti = claims.get("jti")
        if not jti:
            raise AuthenticationError("Invalid access token")
        if await self.store.get(self._key(jti)):
            raise AuthenticationError("Access token has been revoked")
            
        user_id = claims.get("sub")
        if user_id:
            revoked_at_str = await self.store.get(f"auth:revoked_all_access:{user_id}")
            if revoked_at_str:
                revoked_at = int(revoked_at_str)
                iat = claims.get("iat", 0)
                if iat <= revoked_at:
                    raise AuthenticationError("Access token has been revoked due to security event")

    @staticmethod
    def _key(jti: str) -> str:
        return f"auth:revoked_access:{jti}"
