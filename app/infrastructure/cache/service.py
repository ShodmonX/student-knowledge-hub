from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock
from typing import Any

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - optional dependency in local test env
    Redis = None

    class RedisError(Exception):
        pass


logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime


class InMemoryCacheBackend:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = Lock()

    async def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            if entry.expires_at <= datetime.now(UTC):
                self._entries.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )

    async def invalidate(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in list(self._entries):
                if key.startswith(prefix):
                    self._entries.pop(key, None)


class RedisCacheBackend:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.client: Redis | None = None

    async def connect(self) -> None:
        if Redis is None:
            raise RuntimeError("redis package is not installed")
        self.client = Redis.from_url(self.redis_url, decode_responses=True)
        await self.client.ping()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def get(self, key: str) -> Any | None:
        if self.client is None:
            return None
        payload = await self.client.get(key)
        if payload is None:
            return None
        return json.loads(payload)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self.client is None:
            return
        await self.client.set(key, json.dumps(value), ex=ttl_seconds)

    async def invalidate(self, key: str) -> None:
        if self.client is None:
            return
        await self.client.delete(key)

    async def invalidate_prefix(self, prefix: str) -> None:
        if self.client is None:
            return
        async for key in self.client.scan_iter(match=f"{prefix}*"):
            await self.client.delete(key)


class CacheService:
    def __init__(self) -> None:
        self.backend: InMemoryCacheBackend | RedisCacheBackend = InMemoryCacheBackend()
        self.is_redis_enabled = False

    async def initialize(self, redis_url: str | None) -> None:
        if not redis_url:
            self.backend = InMemoryCacheBackend()
            self.is_redis_enabled = False
            return
        redis_backend = RedisCacheBackend(redis_url)
        try:
            await redis_backend.connect()
        except (RedisError, RuntimeError) as exc:
            logger.warning("Redis cache unavailable, falling back to in-memory cache: %s", exc)
            self.backend = InMemoryCacheBackend()
            self.is_redis_enabled = False
            return
        self.backend = redis_backend
        self.is_redis_enabled = True

    async def close(self) -> None:
        if isinstance(self.backend, RedisCacheBackend):
            await self.backend.close()

    async def get(self, key: str) -> Any | None:
        return await self.backend.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self.backend.set(key, value, ttl_seconds)

    async def invalidate(self, key: str) -> None:
        await self.backend.invalidate(key)

    async def invalidate_prefix(self, prefix: str) -> None:
        await self.backend.invalidate_prefix(prefix)


@lru_cache
def get_cache() -> CacheService:
    return CacheService()
