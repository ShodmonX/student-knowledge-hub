from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - optional dependency in local test env
    Redis = None

    class RedisError(Exception):
        pass


logger = logging.getLogger(__name__)


class NullCacheBackend:
    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        return None

    async def invalidate(self, key: str) -> None:
        return None

    async def invalidate_prefix(self, prefix: str) -> None:
        return None


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
        self.backend: NullCacheBackend | RedisCacheBackend = NullCacheBackend()
        self.is_redis_enabled = False

    async def initialize(self, redis_url: str | None) -> None:
        if not redis_url:
            self.backend = NullCacheBackend()
            self.is_redis_enabled = False
            return

        redis_backend = RedisCacheBackend(redis_url)
        try:
            await redis_backend.connect()
        except (RedisError, RuntimeError) as exc:
            logger.warning("Redis cache unavailable, disabling cache: %s", exc)
            self.backend = NullCacheBackend()
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
