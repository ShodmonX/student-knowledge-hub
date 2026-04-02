import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
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
