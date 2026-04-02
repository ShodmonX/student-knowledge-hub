from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.bootstrap.backup_scheduler import BackupScheduler
from app.bootstrap.backup_service import BackupError
from app.core.config import Settings


@dataclass
class FakeManifest:
    backup_id: str


@dataclass
class FakeResult:
    manifest: FakeManifest
    local_deleted: list[str]
    offsite_deleted: list[str]


def build_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "db_url": "postgresql+asyncpg://postgres:secret@localhost:5432/student_knowledge_hub",
        "backup_local_root": str(tmp_path / "test_backups"),
        "backup_schedule_enabled": True,
        "backup_interval_seconds": 300,
        "backup_run_on_start": True,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


def test_backup_scheduler_exits_when_disabled(tmp_path):
    logs: list[str] = []
    scheduler = BackupScheduler(
        settings=build_settings(tmp_path, backup_schedule_enabled=False),
        log_fn=logs.append,
    )

    run_count = scheduler.run()

    assert run_count == 0
    assert logs == ["Backup scheduler disabled; exiting."]


def test_backup_scheduler_runs_immediately_and_on_interval(tmp_path):
    logs: list[str] = []
    sleep_calls: list[float] = []
    triggers: list[str] = []

    class FakeBackupService:
        def run_backup(self, trigger: str = "manual"):
            triggers.append(trigger)
            return FakeResult(
                manifest=FakeManifest(backup_id=f"backup-{len(triggers)}"),
                local_deleted=[],
                offsite_deleted=[],
            )

    scheduler = BackupScheduler(
        settings=build_settings(tmp_path, backup_interval_seconds=120, backup_run_on_start=True),
        service_factory=FakeBackupService,
        sleep_fn=sleep_calls.append,
        log_fn=logs.append,
    )

    run_count = scheduler.run(max_runs=2)

    assert run_count == 2
    assert triggers == ["scheduled", "scheduled"]
    assert sleep_calls == [120]
    assert logs == [
        "Backup created: backup-1 (local_deleted=0, offsite_deleted=0)",
        "Backup created: backup-2 (local_deleted=0, offsite_deleted=0)",
    ]


def test_backup_scheduler_waits_before_first_run_when_disabled_on_start(tmp_path):
    sleep_calls: list[float] = []
    triggers: list[str] = []

    class FakeBackupService:
        def run_backup(self, trigger: str = "manual"):
            triggers.append(trigger)
            return FakeResult(
                manifest=FakeManifest(backup_id="backup-1"),
                local_deleted=[],
                offsite_deleted=[],
            )

    scheduler = BackupScheduler(
        settings=build_settings(tmp_path, backup_interval_seconds=45, backup_run_on_start=False),
        service_factory=FakeBackupService,
        sleep_fn=sleep_calls.append,
        log_fn=lambda message: None,
    )

    run_count = scheduler.run(max_runs=1)

    assert run_count == 1
    assert sleep_calls == [45]
    assert triggers == ["scheduled"]


def test_backup_scheduler_logs_and_survives_backup_error(tmp_path):
    logs: list[str] = []

    class FakeBackupService:
        def run_backup(self, trigger: str = "manual"):
            raise BackupError("offsite listing failed")

    scheduler = BackupScheduler(
        settings=build_settings(tmp_path, backup_run_on_start=True),
        service_factory=FakeBackupService,
        log_fn=logs.append,
    )

    run_count = scheduler.run(max_runs=1)

    assert run_count == 1
    assert logs == ["Backup failed: offsite listing failed"]


def test_backup_scheduler_stops_cleanly_when_stop_requested(tmp_path):
    logs: list[str] = []
    sleep_calls: list[float] = []

    scheduler = BackupScheduler(
        settings=build_settings(tmp_path, backup_run_on_start=False, backup_interval_seconds=30),
        sleep_fn=sleep_calls.append,
        stop_requested=lambda: True,
        log_fn=logs.append,
    )

    run_count = scheduler.run()

    assert run_count == 0
    assert sleep_calls == []
    assert logs == ["Backup scheduler stopping."]
