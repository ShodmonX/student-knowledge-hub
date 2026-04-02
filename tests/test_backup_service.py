from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.bootstrap.backup_service import BackupError, BackupManifest, BackupService, ClientError
from app.core.config import Settings
from app.core.exceptions import ResourceNotFound


@dataclass
class FakeCompletedProcess:
    stdout: str = ""
    stderr: str = ""


class FakePaginator:
    def __init__(self, responses):
        self.responses = responses

    def paginate(self, **kwargs):
        return self.responses


def build_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "db_url": "postgresql+asyncpg://postgres:secret@localhost:5432/student_knowledge_hub",
        "backup_local_root": str(tmp_path / "test_backups"),
        "backup_filename_prefix": "student-knowledge-hub",
        "backup_timeout_seconds": 120,
        "backup_verify_restore": True,
        "backup_retention_local": 2,
        "backup_offsite_enabled": False,
        "backup_retention_offsite": 2,
        "backup_s3_prefix": "production/postgres",
        "s3_bucket": None,
        "s3_region": None,
        "s3_endpoint_url": None,
        "s3_access_key_id": None,
        "s3_secret_access_key": None,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


def test_backup_service_creates_local_dump_manifest_and_verifies(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    service = BackupService(settings)
    commands: list[list[str]] = []

    def fake_run(command, env, check, capture_output, text, timeout):
        commands.append(command)
        if command[0] == "pg_dump":
            dump_arg = next(item for item in command if item.startswith("--file="))
            dump_path = Path(dump_arg.split("=", 1)[1])
            dump_path.write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    result = service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))

    assert len(commands) == 2
    assert commands[0][0] == "pg_dump"
    assert commands[1][0] == "pg_restore"
    manifest = result.manifest
    assert manifest.verified is True
    assert manifest.database_name == "student_knowledge_hub"
    assert manifest.offsite_enabled is False
    assert result.local_deleted == []
    manifest_path = Path(manifest.local_manifest_path)
    assert manifest_path.exists() is True
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["checksum_sha256"] == manifest.checksum_sha256
    assert loaded["size_bytes"] == len(b"backup-bytes")
    assert loaded["trigger"] == "manual"


def test_backup_service_skips_restore_verification_when_disabled(monkeypatch, tmp_path):
    settings = build_settings(tmp_path, backup_verify_restore=False)
    service = BackupService(settings)
    commands: list[list[str]] = []

    def fake_run(command, env, check, capture_output, text, timeout):
        commands.append(command)
        dump_arg = next((item for item in command if item.startswith("--file=")), None)
        if dump_arg:
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    result = service.run_backup(now=datetime(2026, 4, 1, 3, 0, tzinfo=UTC))

    assert [command[0] for command in commands] == ["pg_dump"]
    assert result.manifest.verified is False


def test_backup_service_prunes_old_local_backups(monkeypatch, tmp_path):
    settings = build_settings(tmp_path, backup_retention_local=1, backup_verify_restore=False)
    service = BackupService(settings)

    def fake_run(command, env, check, capture_output, text, timeout):
        dump_arg = next((item for item in command if item.startswith("--file=")), None)
        if dump_arg:
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    first = service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))
    second = service.run_backup(now=datetime(2026, 4, 2, 2, 0, tzinfo=UTC))

    assert Path(second.manifest.local_manifest_path).exists() is True
    assert Path(first.manifest.local_manifest_path).exists() is False
    assert Path(first.manifest.local_dump_path).exists() is False
    assert len(second.local_deleted) == 2


def test_backup_service_uploads_and_prunes_offsite(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_verify_restore=False,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
        backup_retention_offsite=1,
    )
    service = BackupService(settings)
    uploaded: list[tuple[str, str, str]] = []
    put_objects: list[str] = []
    deleted: list[str] = []

    class FakeS3Client:
        def upload_file(self, filename, bucket, key):
            uploaded.append((filename, bucket, key))

        def put_object(self, Bucket, Key, Body, ContentType):
            put_objects.append(Key)

        def get_object(self, Bucket, Key):
            return {"Body": type("Body", (), {"read": lambda self: Path(tmp_path / "remote.manifest.json").read_bytes()})()}

        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator(
                [
                    {
                        "Contents": [
                            {"Key": "production/postgres/student-knowledge-hub-20260330T020000Z.dump"},
                            {"Key": "production/postgres/student-knowledge-hub-20260330T020000Z.manifest.json"},
                            {"Key": "production/postgres/student-knowledge-hub-20260331T020000Z.dump"},
                            {"Key": "production/postgres/student-knowledge-hub-20260331T020000Z.manifest.json"},
                        ]
                    },
                    {
                        "Contents": [
                            {"Key": "production/postgres/student-knowledge-hub-20260401T020000Z.dump"},
                            {"Key": "production/postgres/student-knowledge-hub-20260401T020000Z.manifest.json"},
                        ]
                    },
                ]
            )

        def delete_object(self, Bucket, Key):
            deleted.append(Key)

        def download_file(self, Bucket, Key, Filename):
            Path(Filename).write_bytes(b"backup-bytes")

    fake_manifest = BackupManifest(
        backup_id="student-knowledge-hub-20260401T020000Z",
        created_at="2026-04-01T02:00:00+00:00",
        database_name="student_knowledge_hub",
        dump_format="custom",
        checksum_sha256="277089d91c0bdf4f2e6862ba7e4a07605119431f5d13f726dd352b06f1b206a9",
        size_bytes=len(b"backup-bytes"),
        verified=False,
        trigger="manual",
        local_dump_path=str(tmp_path / "missing.dump"),
        local_manifest_path=str(tmp_path / "remote.manifest.json"),
        offsite_enabled=True,
        offsite_bucket="backup-bucket",
        offsite_dump_key="production/postgres/student-knowledge-hub-20260401T020000Z.dump",
        offsite_manifest_key="production/postgres/student-knowledge-hub-20260401T020000Z.manifest.json",
    )
    (tmp_path / "remote.manifest.json").write_text(fake_manifest.to_json(), encoding="utf-8")

    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    def fake_run(command, env, check, capture_output, text, timeout):
        dump_arg = next((item for item in command if item.startswith("--file=")), None)
        if dump_arg:
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    result = service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))

    assert uploaded[0][1] == "backup-bucket"
    assert result.manifest.offsite_bucket == "backup-bucket"
    assert result.manifest.offsite_dump_key is not None
    assert result.manifest.offsite_manifest_key is not None
    assert put_objects == [result.manifest.offsite_manifest_key]
    assert len(result.offsite_deleted) == 4
    assert deleted == result.offsite_deleted


def test_backup_service_raises_for_invalid_database_url(tmp_path):
    settings = build_settings(tmp_path, db_url="sqlite+aiosqlite:///./test.db")
    service = BackupService(settings)

    with pytest.raises(BackupError):
        service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))


def test_backup_service_raises_when_commands_fail(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    service = BackupService(settings)

    def fake_run(command, env, check, capture_output, text, timeout):
        raise subprocess.CalledProcessError(1, command, stderr="pg_dump failed")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    with pytest.raises(BackupError, match="pg_dump failed"):
        service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))


def test_backup_service_raises_when_commands_missing(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    service = BackupService(settings)

    def fake_run(command, env, check, capture_output, text, timeout):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    with pytest.raises(BackupError, match="Required command not found"):
        service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))


def test_backup_service_raises_for_missing_offsite_settings(monkeypatch, tmp_path):
    settings = build_settings(tmp_path, backup_offsite_enabled=True, backup_verify_restore=False)
    service = BackupService(settings)

    def fake_run(command, env, check, capture_output, text, timeout):
        dump_arg = next((item for item in command if item.startswith("--file=")), None)
        if dump_arg:
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    with pytest.raises(BackupError, match="S3 storage is not fully configured for backups"):
        service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))


def test_backup_service_load_manifest_and_remote_stem(tmp_path):
    settings = build_settings(tmp_path)
    service = BackupService(settings)
    manifest_path = tmp_path / "backup.manifest.json"
    manifest = BackupManifest(
        backup_id="sample",
        created_at="2026-04-01T02:00:00+00:00",
        database_name="db",
        dump_format="custom",
        checksum_sha256="abc",
        size_bytes=10,
        verified=True,
        trigger="manual",
        local_dump_path="/tmp/backup.dump",
        local_manifest_path=str(manifest_path),
        offsite_enabled=False,
    )
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")

    loaded = service.load_manifest(manifest_path)

    assert loaded.backup_id == "sample"
    assert service._remote_backup_stem("production/postgres/sample.dump") == "production/postgres/sample"
    assert (
        service._remote_backup_stem("production/postgres/sample.manifest.json")
        == "production/postgres/sample"
    )
    assert service._remote_backup_stem("production/postgres/sample.txt") is None


def test_backup_service_lists_and_gets_local_and_remote_backups(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    service = BackupService(settings)
    local_root = Path(settings.backup_local_root) / "daily"
    local_root.mkdir(parents=True, exist_ok=True)
    local_manifest = BackupManifest(
        backup_id="local-backup",
        created_at="2026-04-02T02:00:00+00:00",
        database_name="student_knowledge_hub",
        dump_format="custom",
        checksum_sha256="abc",
        size_bytes=10,
        verified=True,
        trigger="manual",
        local_dump_path=str(local_root / "local-backup.dump"),
        local_manifest_path=str(local_root / "local-backup.manifest.json"),
        offsite_enabled=True,
        offsite_bucket="backup-bucket",
        offsite_dump_key="production/postgres/local-backup.dump",
        offsite_manifest_key="production/postgres/local-backup.manifest.json",
    )
    Path(local_manifest.local_manifest_path).write_text(local_manifest.to_json(), encoding="utf-8")
    Path(local_manifest.local_dump_path).write_bytes(b"local")
    remote_manifest = BackupManifest(
        backup_id="remote-only-backup",
        created_at="2026-04-01T02:00:00+00:00",
        database_name="student_knowledge_hub",
        dump_format="custom",
        checksum_sha256="def",
        size_bytes=12,
        verified=True,
        trigger="manual",
        local_dump_path=str(local_root / "remote-only-backup.dump"),
        local_manifest_path=str(local_root / "remote-only-backup.manifest.json"),
        offsite_enabled=True,
        offsite_bucket="backup-bucket",
        offsite_dump_key="production/postgres/remote-only-backup.dump",
        offsite_manifest_key="production/postgres/remote-only-backup.manifest.json",
    )

    class FakeS3Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator([{"Contents": [{"Key": remote_manifest.offsite_manifest_key}]}])

        def get_object(self, Bucket, Key):
            return {"Body": type("Body", (), {"read": lambda self: remote_manifest.to_json().encode("utf-8")})()}

    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    records = service.list_backups()

    assert [record.manifest.backup_id for record in records] == ["local-backup", "remote-only-backup"]
    assert records[0].available_local is True
    assert records[0].available_offsite is True
    assert records[1].available_local is False
    assert records[1].available_offsite is True
    assert service.get_backup("remote-only-backup").manifest.backup_id == "remote-only-backup"
    with pytest.raises(ResourceNotFound):
        service.get_backup("missing")


def test_backup_service_restore_creates_pre_restore_backup_and_restores(monkeypatch, tmp_path):
    settings = build_settings(tmp_path, backup_verify_restore=True)
    service = BackupService(settings)
    commands: list[list[str]] = []

    def fake_run(command, env, check, capture_output, text, timeout):
        commands.append(command)
        if command[0] == "pg_dump":
            dump_arg = next(item for item in command if item.startswith("--file="))
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    created = service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))
    commands.clear()

    restored = service.restore_backup(created.manifest.backup_id, now=datetime(2026, 4, 2, 2, 0, tzinfo=UTC))

    assert restored.pre_restore_backup.trigger == "pre-restore"
    assert restored.restored_backup.manifest.backup_id == created.manifest.backup_id
    assert [command[0] for command in commands] == [
        "pg_dump",
        "pg_restore",
        "pg_restore",
        "psql",
        "dropdb",
        "createdb",
        "pg_restore",
    ]


def test_backup_service_restore_verifies_offsite_dump_before_restore(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    service = BackupService(settings)
    local_root = Path(settings.backup_local_root) / "daily"
    local_root.mkdir(parents=True, exist_ok=True)
    checksum = "3f75e04c360b46d235f2fc1059fc5a3b29c02152b3e261f878d3875cf7f5277c"
    remote_manifest = BackupManifest(
        backup_id="remote-restore",
        created_at="2026-04-01T02:00:00+00:00",
        database_name="student_knowledge_hub",
        dump_format="custom",
        checksum_sha256=checksum,
        size_bytes=len(b"backup-bytes"),
        verified=True,
        trigger="manual",
        local_dump_path=str(local_root / "remote-restore.dump"),
        local_manifest_path=str(local_root / "remote-restore.manifest.json"),
        offsite_enabled=True,
        offsite_bucket="backup-bucket",
        offsite_dump_key="production/postgres/remote-restore.dump",
        offsite_manifest_key="production/postgres/remote-restore.manifest.json",
    )
    Path(remote_manifest.local_manifest_path).write_text(remote_manifest.to_json(), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, env, check, capture_output, text, timeout):
        commands.append(command)
        if command[0] == "pg_dump":
            dump_arg = next(item for item in command if item.startswith("--file="))
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    class FakeS3Client:
        def upload_file(self, filename, bucket, key):
            return None

        def put_object(self, Bucket, Key, Body, ContentType):
            return None

        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator([{"Contents": [{"Key": remote_manifest.offsite_manifest_key}]}])

        def get_object(self, Bucket, Key):
            return {"Body": type("Body", (), {"read": lambda self: remote_manifest.to_json().encode("utf-8")})()}

        def delete_object(self, Bucket, Key):
            return None

        def download_file(self, Bucket, Key, Filename):
            Path(Filename).write_bytes(b"backup-bytes")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)
    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    result = service.restore_backup("remote-restore", now=datetime(2026, 4, 2, 2, 0, tzinfo=UTC))

    assert result.restored_backup.available_offsite is True
    assert result.pre_restore_backup.trigger == "pre-restore"


def test_backup_service_restore_rejects_checksum_mismatch(monkeypatch, tmp_path):
    settings = build_settings(tmp_path, backup_verify_restore=False)
    service = BackupService(settings)
    local_root = Path(settings.backup_local_root) / "daily"
    local_root.mkdir(parents=True, exist_ok=True)
    manifest = BackupManifest(
        backup_id="bad-restore",
        created_at="2026-04-01T02:00:00+00:00",
        database_name="student_knowledge_hub",
        dump_format="custom",
        checksum_sha256="wrong",
        size_bytes=10,
        verified=True,
        trigger="manual",
        local_dump_path=str(local_root / "bad-restore.dump"),
        local_manifest_path=str(local_root / "bad-restore.manifest.json"),
        offsite_enabled=False,
    )
    Path(manifest.local_manifest_path).write_text(manifest.to_json(), encoding="utf-8")
    Path(manifest.local_dump_path).write_bytes(b"backup-bytes")

    def fake_run(command, env, check, capture_output, text, timeout):
        if command[0] == "pg_dump":
            dump_arg = next(item for item in command if item.startswith("--file="))
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    with pytest.raises(BackupError, match="checksum verification failed"):
        service.restore_backup("bad-restore", now=datetime(2026, 4, 2, 2, 0, tzinfo=UTC))


def test_backup_service_list_backups_ignores_offsite_listing_errors(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    service = BackupService(settings)

    class ErrorPaginator:
        def paginate(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "ListObjectsV2")

    class FakeS3Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return ErrorPaginator()

    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    assert service.list_backups() == []


def test_backup_service_treats_missing_offsite_prefix_as_empty_during_prune(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_verify_restore=False,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
        backup_retention_offsite=1,
    )
    service = BackupService(settings)

    class ErrorPaginator:
        def paginate(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "ListObjectsV2")

    class FakeS3Client:
        def upload_file(self, filename, bucket, key):
            return None

        def put_object(self, Bucket, Key, Body, ContentType):
            return None

        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return ErrorPaginator()

    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    def fake_run(command, env, check, capture_output, text, timeout):
        dump_arg = next((item for item in command if item.startswith("--file=")), None)
        if dump_arg:
            Path(dump_arg.split("=", 1)[1]).write_bytes(b"backup-bytes")
        return FakeCompletedProcess(stdout="ok")

    monkeypatch.setattr("app.bootstrap.backup_service.subprocess.run", fake_run)

    result = service.run_backup(now=datetime(2026, 4, 1, 2, 0, tzinfo=UTC))

    assert result.offsite_deleted == []


def test_backup_service_list_backups_ignores_paginator_iteration_nosuchkey(monkeypatch, tmp_path):
    settings = build_settings(
        tmp_path,
        backup_offsite_enabled=True,
        s3_bucket="backup-bucket",
        s3_region="fra1",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    service = BackupService(settings)

    class IteratorErrorPaginator:
        def paginate(self, **kwargs):
            class _BrokenIterator:
                def __iter__(self_inner):
                    raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "ListObjectsV2")

            return _BrokenIterator()

    class FakeS3Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return IteratorErrorPaginator()

    monkeypatch.setattr(
        "app.bootstrap.backup_service.boto3",
        type("FakeBoto3", (), {"client": lambda *a, **k: FakeS3Client()})(),
    )

    assert service.list_backups() == []
