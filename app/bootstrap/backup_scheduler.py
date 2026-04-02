from __future__ import annotations

import time
from collections.abc import Callable

from app.bootstrap.backup_service import BackupError, BackupService
from app.core.config import Settings, get_settings


class BackupScheduler:
    def __init__(
        self,
        settings: Settings | None = None,
        service_factory: Callable[[], BackupService] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.service_factory = service_factory or (lambda: BackupService(self.settings))
        self.sleep_fn = sleep_fn or time.sleep
        self.stop_requested = stop_requested or (lambda: False)
        self.log_fn = log_fn or print

    def run(self, max_runs: int | None = None) -> int:
        if not self.settings.backup_schedule_enabled:
            self.log_fn("Backup scheduler disabled; exiting.")
            return 0

        interval = max(int(self.settings.backup_interval_seconds), 1)
        run_count = 0

        if self.settings.backup_run_on_start:
            self._run_once()
            run_count += 1
            if max_runs is not None and run_count >= max_runs:
                return run_count

        while True:
            if self.stop_requested():
                self.log_fn("Backup scheduler stopping.")
                return run_count
            self.sleep_fn(interval)
            if self.stop_requested():
                self.log_fn("Backup scheduler stopping.")
                return run_count
            self._run_once()
            run_count += 1
            if max_runs is not None and run_count >= max_runs:
                return run_count

    def _run_once(self) -> None:
        try:
            result = self.service_factory().run_backup(trigger="scheduled")
        except BackupError as exc:
            self.log_fn(f"Backup failed: {exc}")
            return
        self.log_fn(
            f"Backup created: {result.manifest.backup_id} "
            f"(local_deleted={len(result.local_deleted)}, offsite_deleted={len(result.offsite_deleted)})"
        )
