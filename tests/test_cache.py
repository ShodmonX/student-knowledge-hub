import pytest

from app.core import cache
from app.core.cache import CacheService, NullCacheBackend, RedisCacheBackend


class FakeRedis:
    def __init__(self, url: str, decode_responses: bool) -> None:
        self.url = url
        self.decode_responses = decode_responses
        self.values: dict[str, str] = {}
        self.closed = False

    @classmethod
    def from_url(cls, url: str, decode_responses: bool):
        return cls(url, decode_responses)

    async def ping(self):
        return True

    async def aclose(self):
        self.closed = True

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int):
        self.values[key] = value

    async def delete(self, key: str):
        self.values.pop(key, None)

    async def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key


class BrokenRedis(FakeRedis):
    async def ping(self):
        raise RuntimeError("redis unavailable")


@pytest.mark.asyncio
async def test_redis_cache_backend_roundtrip_and_prefix_invalidation(monkeypatch):
    monkeypatch.setattr(cache, "Redis", FakeRedis)
    service = CacheService()

    await service.initialize("redis://unit-test")

    assert service.is_redis_enabled is True
    assert isinstance(service.backend, RedisCacheBackend)
    assert service.backend.client.url == "redis://unit-test"
    await service.set("item", {"enabled": True}, 30)
    assert await service.get("item") == {"enabled": True}

    await service.set("prefix:a", {"id": "a"}, 30)
    await service.set("prefix:b", {"id": "b"}, 30)
    await service.invalidate_prefix("prefix:")
    assert await service.get("prefix:a") is None
    assert await service.get("prefix:b") is None

    await service.invalidate("item")
    assert await service.get("item") is None
    await service.close()
    assert service.backend.client is None


@pytest.mark.asyncio
async def test_cache_service_disables_redis_when_connect_fails(monkeypatch):
    monkeypatch.setattr(cache, "Redis", BrokenRedis)
    service = CacheService()

    await service.initialize("redis://broken")

    assert service.is_redis_enabled is False
    assert isinstance(service.backend, NullCacheBackend)
