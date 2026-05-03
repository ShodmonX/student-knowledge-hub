import pytest


@pytest.mark.asyncio
async def test_lifespan_initializes_and_closes_cache(monkeypatch):
    import app.main as main_module

    calls = []

    class FakeCache:
        is_redis_enabled = False

        async def initialize(self, redis_url):
            calls.append(("initialize", redis_url))

        async def close(self):
            calls.append(("close", None))

    fake_cache = FakeCache()
    monkeypatch.setattr(main_module, "get_cache", lambda: fake_cache)

    async with main_module.lifespan(main_module.app):
        calls.append(("inside", None))

    assert calls == [
        ("initialize", main_module.settings.redis_url),
        ("inside", None),
        ("close", None),
    ]


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "redis_cache": False}


@pytest.mark.asyncio
async def test_health_live(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "redis_cache": False}


@pytest.mark.asyncio
async def test_health_ready(client, monkeypatch):
    async def fake_database_health():
        return {"status": "ok"}

    async def fake_storage_health():
        return {"status": "ok", "backend": "local"}

    monkeypatch.setattr("app.main._database_health", fake_database_health)
    monkeypatch.setattr("app.main._storage_health", fake_storage_health)
    monkeypatch.setattr("app.main._cache_health", lambda: {"status": "disabled", "backend": "none", "enabled": False})
    monkeypatch.setattr(
        "app.main._backup_health",
        lambda: {
            "status": "ok",
            "schedule_enabled": False,
            "retention_local": 7,
            "retention_offsite": 14,
            "latest_backup_id": None,
            "latest_backup_at": None,
        },
    )

    response = await client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    import app.main as main_module

    assert payload["environment"] == main_module.settings.app_env
    assert payload["services"]["database"]["status"] == "ok"
    assert payload["services"]["cache"]["status"] == "disabled"
    assert payload["services"]["storage"]["status"] == "ok"
    assert payload["services"]["backups"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_database_check_fails(client, monkeypatch):
    async def fake_database_health():
        return {"status": "error", "detail": "db down"}

    monkeypatch.setattr("app.main._database_health", fake_database_health)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["services"]["database"]["detail"] == "db down"


@pytest.mark.asyncio
async def test_health_ready_reports_degraded_when_scheduled_backups_missing(client, monkeypatch):
    import app.main as main_module

    async def fake_database_health():
        return {"status": "ok"}

    async def fake_storage_health():
        return {"status": "ok", "backend": "local"}

    original = main_module.settings.backup_schedule_enabled
    main_module.settings.backup_schedule_enabled = True
    monkeypatch.setattr("app.main._database_health", fake_database_health)
    monkeypatch.setattr("app.main._storage_health", fake_storage_health)
    monkeypatch.setattr("app.main._cache_health", lambda: {"status": "disabled", "backend": "none", "enabled": False})
    monkeypatch.setattr("app.main.BackupService.list_backups", lambda self: [])

    response = await client.get("/health/ready")

    main_module.settings.backup_schedule_enabled = original
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["services"]["backups"]["detail"] == "No backups found yet"


@pytest.mark.asyncio
async def test_database_health_ok(monkeypatch):
    import app.main as main_module

    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(main_module, "engine", FakeEngine())

    assert await main_module._database_health() == {"status": "ok"}


def test_cache_health_reports_degraded_when_redis_configured_but_disabled(monkeypatch):
    import app.main as main_module

    class FakeCache:
        is_redis_enabled = False

    original_redis_url = main_module.settings.redis_url
    main_module.settings.redis_url = "redis://redis:6379/0"
    monkeypatch.setattr(main_module, "get_cache", lambda: FakeCache())

    try:
        assert main_module._cache_health() == {
            "status": "degraded",
            "backend": "redis",
            "enabled": False,
        }
    finally:
        main_module.settings.redis_url = original_redis_url


def test_cache_health_reports_enabled_redis(monkeypatch):
    import app.main as main_module

    class FakeCache:
        is_redis_enabled = True

    monkeypatch.setattr(main_module, "get_cache", lambda: FakeCache())

    assert main_module._cache_health() == {
        "status": "ok",
        "backend": "redis",
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_storage_health_reports_missing_local_root(tmp_path, monkeypatch):
    import app.main as main_module

    original_backend = main_module.settings.storage_backend
    original_root = main_module.settings.storage_root
    main_module.settings.storage_backend = "local"
    main_module.settings.storage_root = str(tmp_path / "missing-storage")
    monkeypatch.setattr(main_module, "StorageService", lambda: object())

    try:
        assert await main_module._storage_health() == {
            "status": "error",
            "backend": "local",
            "detail": "Storage root is missing",
        }
    finally:
        main_module.settings.storage_backend = original_backend
        main_module.settings.storage_root = original_root


def test_backup_health_reports_backup_service_error(monkeypatch):
    import app.main as main_module

    original_schedule_enabled = main_module.settings.backup_schedule_enabled
    main_module.settings.backup_schedule_enabled = True

    def raise_backup_error(self):
        raise main_module.BackupError("backup root unavailable")

    monkeypatch.setattr(main_module.BackupService, "list_backups", raise_backup_error)

    try:
        result = main_module._backup_health()
    finally:
        main_module.settings.backup_schedule_enabled = original_schedule_enabled

    assert result == {
        "status": "degraded",
        "schedule_enabled": True,
        "detail": "backup root unavailable",
        "latest_backup_id": None,
        "latest_backup_at": None,
    }


def test_backup_health_is_ok_when_schedule_disabled_and_no_backups(monkeypatch):
    import app.main as main_module

    original_schedule_enabled = main_module.settings.backup_schedule_enabled
    main_module.settings.backup_schedule_enabled = False
    monkeypatch.setattr(main_module.BackupService, "list_backups", lambda self: [])

    try:
        result = main_module._backup_health()
    finally:
        main_module.settings.backup_schedule_enabled = original_schedule_enabled

    assert result["status"] == "ok"
    assert result["schedule_enabled"] is False
    assert result["latest_backup_id"] is None
    assert result["latest_backup_at"] is None
