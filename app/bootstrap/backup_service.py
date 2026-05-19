from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine.url import make_url

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceNotFound

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - optional in local env until dependency install
    boto3 = None

    class BotoCoreError(Exception):
        pass

    class ClientError(Exception):
        pass


class BackupError(RuntimeError):
    pass


BACKUP_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}$")
UNSUPPORTED_RESTORE_SET_COMMANDS = {
    "SET transaction_timeout = 0;",
}


@dataclass(frozen=True)
class DatabaseConnectionInfo:
    database: str
    username: str
    password: str | None
    host: str
    port: int


@dataclass
class BackupManifest:
    backup_id: str
    created_at: str
    database_name: str
    dump_format: str
    checksum_sha256: str
    size_bytes: int
    verified: bool
    trigger: str
    local_dump_path: str
    local_manifest_path: str
    offsite_enabled: bool
    offsite_bucket: str | None = None
    offsite_dump_key: str | None = None
    offsite_manifest_key: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


@dataclass
class BackupResult:
    manifest: BackupManifest
    local_deleted: list[str]
    offsite_deleted: list[str]


@dataclass
class BackupRecord:
    manifest: BackupManifest
    available_local: bool
    available_offsite: bool


@dataclass
class BackupRestoreResult:
    restored_backup: BackupRecord
    pre_restore_backup: BackupManifest
    restored_at: str


class BackupService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run_backup(self, now: datetime | None = None, trigger: str = "manual") -> BackupResult:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        connection_info = self._build_connection_info()
        dump_path, manifest_path, backup_id = self._build_backup_paths(timestamp, trigger)

        dump_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_pg_dump(connection_info, dump_path)

        verified = False
        if self.settings.backup_verify_restore:
            self._verify_dump(dump_path)
            verified = True

        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=timestamp.isoformat(),
            database_name=connection_info.database,
            dump_format="custom",
            checksum_sha256=self._compute_sha256(dump_path),
            size_bytes=dump_path.stat().st_size,
            verified=verified,
            trigger=trigger,
            local_dump_path=str(dump_path),
            local_manifest_path=str(manifest_path),
            offsite_enabled=self._offsite_enabled(),
        )
        manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")

        offsite_deleted: list[str] = []
        if self._offsite_enabled():
            offsite_deleted = self._upload_and_prune_offsite(manifest, dump_path, manifest_path)
            manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")

        local_deleted = self._prune_local_backups()
        return BackupResult(manifest=manifest, local_deleted=local_deleted, offsite_deleted=offsite_deleted)

    def load_manifest(self, manifest_path: Path) -> BackupManifest:
        return BackupManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))

    def list_backups(self) -> list[BackupRecord]:
        records: dict[str, BackupRecord] = {}
        for manifest_path in self._list_local_manifests():
            try:
                manifest = self.load_manifest(manifest_path)
                self._validate_manifest_record(manifest, manifest_path)
            except BackupError:
                continue
            records[manifest.backup_id] = BackupRecord(
                manifest=manifest,
                available_local=Path(manifest.local_dump_path).exists(),
                available_offsite=self._offsite_enabled() and bool(manifest.offsite_dump_key),
            )

        if self._offsite_enabled():
            try:
                client = self._build_backup_s3_client()
                for manifest in self._list_offsite_manifests(client):
                    existing = records.get(manifest.backup_id)
                    if existing:
                        existing.available_offsite = True
                        continue
                    records[manifest.backup_id] = BackupRecord(
                        manifest=manifest,
                        available_local=Path(manifest.local_dump_path).exists(),
                        available_offsite=True,
                    )
            except BackupError:
                pass

        return sorted(records.values(), key=lambda item: item.manifest.created_at, reverse=True)

    def get_backup(self, backup_id: str) -> BackupRecord:
        self._validate_backup_id(backup_id)
        for record in self.list_backups():
            if record.manifest.backup_id == backup_id:
                return record
        raise ResourceNotFound("Backup not found")

    def restore_backup(self, backup_id: str, now: datetime | None = None) -> BackupRestoreResult:
        record = self.get_backup(backup_id)
        pre_restore = self.run_backup(now=now, trigger="pre-restore").manifest
        dump_path, temp_paths = self._prepare_restore_dump(record)
        try:
            self._verify_backup_integrity(record.manifest, dump_path)
            self._restore_dump(self._build_connection_info(), dump_path)
        finally:
            for path in temp_paths:
                path.unlink(missing_ok=True)
        return BackupRestoreResult(
            restored_backup=record,
            pre_restore_backup=pre_restore,
            restored_at=(now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        )

    def _build_connection_info(self) -> DatabaseConnectionInfo:
        url = make_url(self.settings.db_url)
        if not url.drivername.startswith("postgresql"):
            raise BackupError("Backups are only supported for PostgreSQL databases")
        if not url.database or not url.username or not url.host:
            raise BackupError("Backup DB URL must include database, username, and host")
        return DatabaseConnectionInfo(
            database=url.database,
            username=url.username,
            password=url.password,
            host=url.host,
            port=url.port or 5432,
        )

    def _build_backup_paths(self, timestamp: datetime, trigger: str) -> tuple[Path, Path, str]:
        backup_id = f"{self.settings.backup_filename_prefix}-{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
        if trigger != "manual":
            backup_id = f"{backup_id}-{trigger}"
        root = Path(self.settings.backup_local_root) / "daily"
        return root / f"{backup_id}.dump", root / f"{backup_id}.manifest.json", backup_id

    def _run_pg_dump(self, connection: DatabaseConnectionInfo, dump_path: Path) -> None:
        command = [
            "pg_dump",
            "--format=custom",
            f"--file={dump_path}",
            "--host",
            connection.host,
            "--port",
            str(connection.port),
            "--username",
            connection.username,
            "--dbname",
            connection.database,
        ]
        env = os.environ.copy()
        if connection.password:
            env["PGPASSWORD"] = connection.password
        self._run_command(command, env)

    def _verify_dump(self, dump_path: Path) -> None:
        self._run_command(["pg_restore", "--list", str(dump_path)], os.environ.copy())

    def _run_command(self, command: list[str], env: dict[str, str]) -> None:
        try:
            subprocess.run(
                command,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.settings.backup_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise BackupError(f"Required command not found: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BackupError(f"Command timed out: {' '.join(command)}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            message = stderr or stdout or f"Command failed: {' '.join(command)}"
            raise BackupError(message) from exc

    def _compute_sha256(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _prune_local_backups(self) -> list[str]:
        manifest_paths = self._list_local_manifests()
        retention = max(self.settings.backup_retention_local, 1)
        stale_paths = manifest_paths[retention:]
        deleted: list[str] = []
        for manifest_path in stale_paths:
            manifest = self.load_manifest(manifest_path)
            dump_path = Path(manifest.local_dump_path)
            for path in (dump_path, manifest_path):
                if path.exists():
                    path.unlink()
                    deleted.append(str(path))
        return deleted

    def _list_local_manifests(self) -> list[Path]:
        root = Path(self.settings.backup_local_root) / "daily"
        manifests = sorted(root.glob("*.manifest.json"), reverse=True)
        return manifests

    def _upload_and_prune_offsite(
        self,
        manifest: BackupManifest,
        dump_path: Path,
        manifest_path: Path,
    ) -> list[str]:
        client = self._build_backup_s3_client()
        bucket = self.settings.s3_bucket or ""
        prefix = (self.settings.backup_s3_prefix or "production/postgres").rstrip("/")

        dump_key = f"{prefix}/{manifest.backup_id}.dump"
        manifest_key = f"{prefix}/{manifest.backup_id}.manifest.json"
        try:
            client.upload_file(str(dump_path), bucket, dump_key)
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=manifest_path.read_bytes(),
                ContentType="application/json",
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise BackupError(f"Offsite backup upload failed: {exc}") from exc

        manifest.offsite_bucket = bucket
        manifest.offsite_dump_key = dump_key
        manifest.offsite_manifest_key = manifest_key

        return self._prune_offsite_backups(client)

    def _offsite_enabled(self) -> bool:
        return getattr(self.settings, "storage_backend", "local") == "s3"

    def _build_backup_s3_client(self):
        if not self._offsite_enabled():
            raise BackupError("S3 backup storage is disabled when STORAGE_BACKEND is local")
        if boto3 is None:
            raise BackupError("boto3 is not installed")

        required = {
            "s3_bucket": self.settings.s3_bucket,
            "s3_region": self.settings.s3_region,
            "s3_endpoint_url": self.settings.s3_endpoint_url,
            "s3_access_key_id": self.settings.s3_access_key_id,
            "s3_secret_access_key": self.settings.s3_secret_access_key,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise BackupError(f"S3 storage is not fully configured for backups: {', '.join(missing)}")

        return boto3.client(
            "s3",
            region_name=self.settings.s3_region,
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
        )

    def _prune_offsite_backups(self, client) -> list[str]:
        retention = max(self.settings.backup_retention_offsite, 1)

        prefix = (self.settings.backup_s3_prefix or "production/postgres").rstrip("/") + "/"
        bucket = self.settings.s3_bucket or ""
        grouped: dict[str, list[str]] = {}
        try:
            for response in self._paginate_offsite_objects(client, bucket, prefix):
                for item in response.get("Contents", []):
                    key = item["Key"]
                    stem = self._remote_backup_stem(key)
                    if stem is None:
                        continue
                    grouped.setdefault(stem, []).append(key)
        except (BotoCoreError, ClientError, OSError) as exc:
            if self._is_missing_offsite_prefix_error(exc):
                return []
            raise BackupError(f"Offsite backup listing failed: {exc}") from exc

        deleted: list[str] = []
        stale_stems = sorted(grouped, reverse=True)[retention:]
        for stem in stale_stems:
            for key in grouped[stem]:
                client.delete_object(Bucket=bucket, Key=key)
                deleted.append(key)
        return deleted

    def _remote_backup_stem(self, key: str) -> str | None:
        if key.endswith(".manifest.json"):
            return key[: -len(".manifest.json")]
        if key.endswith(".dump"):
            return key[: -len(".dump")]
        return None

    def _list_offsite_manifests(self, client) -> list[BackupManifest]:
        bucket = self.settings.s3_bucket or ""
        prefix = (self.settings.backup_s3_prefix or "production/postgres").rstrip("/") + "/"
        manifests: list[BackupManifest] = []
        try:
            for response in self._paginate_offsite_objects(client, bucket, prefix):
                for item in response.get("Contents", []):
                    key = item["Key"]
                    if not key.endswith(".manifest.json"):
                        continue
                    try:
                        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                    except (BotoCoreError, ClientError, OSError) as exc:
                        raise BackupError(f"Offsite backup manifest read failed: {exc}") from exc
                    manifests.append(BackupManifest(**json.loads(body.decode("utf-8"))))
        except (BotoCoreError, ClientError, OSError) as exc:
            if self._is_missing_offsite_prefix_error(exc):
                return []
            raise BackupError(f"Offsite backup listing failed: {exc}") from exc
        return manifests

    def _paginate_offsite_objects(self, client, bucket: str, prefix: str):
        paginator = client.get_paginator("list_objects_v2")
        return paginator.paginate(Bucket=bucket, Prefix=prefix)

    def _is_missing_offsite_prefix_error(self, exc: Exception) -> bool:
        if not isinstance(exc, ClientError):
            return False
        code = str(exc.response.get("Error", {}).get("Code", "")).strip()
        return code in {"NoSuchKey", "404", "NotFound"}

    def _prepare_restore_dump(self, record: BackupRecord) -> tuple[Path, list[Path]]:
        self._validate_manifest_record(record.manifest, Path(record.manifest.local_manifest_path))
        local_dump_path = Path(record.manifest.local_dump_path)
        if record.available_local and local_dump_path.exists():
            self._validate_restore_dump_path(local_dump_path)
            return local_dump_path, []

        if (
            not self._offsite_enabled()
            or not record.available_offsite
            or not record.manifest.offsite_dump_key
        ):
            raise BackupError("Backup dump is not available for restore")

        self._validate_offsite_dump_key(record.manifest.offsite_dump_key)
        client = self._build_backup_s3_client()
        bucket = record.manifest.offsite_bucket or self.settings.s3_bucket or ""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".dump")
        temp_path = Path(temp_file.name)
        temp_file.close()
        try:
            client.download_file(bucket, record.manifest.offsite_dump_key, str(temp_path))
        except (BotoCoreError, ClientError, OSError) as exc:
            temp_path.unlink(missing_ok=True)
            raise BackupError(f"Offsite backup download failed: {exc}") from exc
        self._validate_restore_dump_path(temp_path, require_allowed_root=False)
        return temp_path, [temp_path]

    def _verify_backup_integrity(self, manifest: BackupManifest, dump_path: Path) -> None:
        if not dump_path.exists():
            raise BackupError("Backup dump file not found")
        checksum = self._compute_sha256(dump_path)
        if checksum != manifest.checksum_sha256:
            raise BackupError("Backup checksum verification failed")
        self._verify_dump(dump_path)

    def _validate_backup_id(self, backup_id: str) -> None:
        if not BACKUP_ID_PATTERN.fullmatch(backup_id):
            raise BackupError("Backup id contains invalid characters")
        if "/" in backup_id or "\\" in backup_id or ".." in backup_id:
            raise BackupError("Backup id contains invalid path segments")

    def _validate_manifest_record(self, manifest: BackupManifest, manifest_path: Path) -> None:
        self._validate_backup_id(manifest.backup_id)
        if manifest.dump_format != "custom":
            raise BackupError("Unsupported backup dump format")
        manifest_path = Path(manifest_path)
        if not manifest_path.name.endswith(".manifest.json"):
            raise BackupError("Backup manifest must use .manifest.json extension")
        if manifest.local_manifest_path:
            recorded_manifest_path = Path(manifest.local_manifest_path)
            if recorded_manifest_path.exists():
                self._ensure_path_allowed(recorded_manifest_path)
        self._validate_restore_dump_path(Path(manifest.local_dump_path), require_exists=False)
        if manifest.offsite_dump_key:
            self._validate_offsite_dump_key(manifest.offsite_dump_key)
        if manifest.offsite_manifest_key:
            self._validate_offsite_manifest_key(manifest.offsite_manifest_key)

    def _validate_restore_dump_path(
        self,
        dump_path: Path,
        *,
        require_allowed_root: bool = True,
        require_exists: bool = True,
    ) -> None:
        if dump_path.name != dump_path.name.strip() or not dump_path.name.endswith(".dump"):
            raise BackupError("Backup dump must use .dump extension")
        if require_allowed_root:
            self._ensure_path_allowed(dump_path)
        if require_exists:
            if not dump_path.exists():
                raise BackupError("Backup dump file not found")
            size = dump_path.stat().st_size
            if size <= 0:
                raise BackupError("Backup dump file is empty")
            if size > self.settings.backup_max_restore_size_bytes:
                raise BackupError("Backup dump exceeds maximum restore size")

    def _ensure_path_allowed(self, path: Path) -> None:
        root = Path(self.settings.backup_local_root).resolve()
        candidate = path.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise BackupError("Backup path is outside the configured backup root") from exc

    def _validate_offsite_dump_key(self, key: str) -> None:
        prefix = (self.settings.backup_s3_prefix or "production/postgres").rstrip("/") + "/"
        if not key.startswith(prefix) or not key.endswith(".dump") or ".." in key:
            raise BackupError("Offsite backup dump key is outside the allowed prefix")

    def _validate_offsite_manifest_key(self, key: str) -> None:
        prefix = (self.settings.backup_s3_prefix or "production/postgres").rstrip("/") + "/"
        if not key.startswith(prefix) or not key.endswith(".manifest.json") or ".." in key:
            raise BackupError("Offsite backup manifest key is outside the allowed prefix")

    def _restore_dump(self, connection: DatabaseConnectionInfo, dump_path: Path) -> None:
        env = os.environ.copy()
        if connection.password:
            env["PGPASSWORD"] = connection.password

        self._terminate_database_connections(connection, env)
        self._drop_and_create_database(connection, env)
        try:
            self._run_pg_restore_direct(connection, dump_path, env)
        except BackupError as exc:
            if not self._is_transaction_timeout_restore_error(str(exc)):
                raise
            self._drop_and_create_database(connection, env)
            self._run_pg_restore_filtered_sql(connection, dump_path, env)

    def _terminate_database_connections(
        self,
        connection: DatabaseConnectionInfo,
        env: dict[str, str],
    ) -> None:
        maintenance_db = "postgres" if connection.database != "postgres" else "template1"
        escaped_db_name = connection.database.replace("'", "''")
        terminate_sql = (
            "SELECT pg_terminate_backend(pid) "
            f"FROM pg_stat_activity WHERE datname = '{escaped_db_name}' AND pid <> pg_backend_pid();"
        )
        self._run_command(
            [
                "psql",
                "--host",
                connection.host,
                "--port",
                str(connection.port),
                "--username",
                connection.username,
                "--dbname",
                maintenance_db,
                "-v",
                "ON_ERROR_STOP=1",
                "--command",
                terminate_sql,
            ],
            env,
        )

    def _drop_and_create_database(
        self,
        connection: DatabaseConnectionInfo,
        env: dict[str, str],
    ) -> None:
        self._run_command(
            [
                "dropdb",
                "--if-exists",
                "--host",
                connection.host,
                "--port",
                str(connection.port),
                "--username",
                connection.username,
                connection.database,
            ],
            env,
        )
        self._run_command(
            [
                "createdb",
                "--host",
                connection.host,
                "--port",
                str(connection.port),
                "--username",
                connection.username,
                "--owner",
                connection.username,
                connection.database,
            ],
            env,
        )

    def _run_pg_restore_direct(
        self,
        connection: DatabaseConnectionInfo,
        dump_path: Path,
        env: dict[str, str],
    ) -> None:
        self._run_command(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--host",
                connection.host,
                "--port",
                str(connection.port),
                "--username",
                connection.username,
                "--dbname",
                connection.database,
                str(dump_path),
            ],
            env,
        )

    def _run_pg_restore_filtered_sql(
        self,
        connection: DatabaseConnectionInfo,
        dump_path: Path,
        env: dict[str, str],
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_sql_path = Path(temp_dir) / "restore.sql"
            filtered_sql_path = Path(temp_dir) / "restore.filtered.sql"
            self._run_command(
                [
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(raw_sql_path),
                    str(dump_path),
                ],
                env,
            )
            with raw_sql_path.open("r", encoding="utf-8", errors="replace") as raw_sql:
                with filtered_sql_path.open("w", encoding="utf-8") as filtered_sql:
                    for line in raw_sql:
                        if line.strip() in UNSUPPORTED_RESTORE_SET_COMMANDS:
                            continue
                        filtered_sql.write(line)
            self._run_command(
                [
                    "psql",
                    "--host",
                    connection.host,
                    "--port",
                    str(connection.port),
                    "--username",
                    connection.username,
                    "--dbname",
                    connection.database,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "--file",
                    str(filtered_sql_path),
                ],
                env,
            )

    @staticmethod
    def _is_transaction_timeout_restore_error(message: str) -> bool:
        return (
            'unrecognized configuration parameter "transaction_timeout"' in message
            or "SET transaction_timeout = 0" in message
        )
