import argparse
from datetime import UTC, datetime

from app.bootstrap.backup_service import BackupService


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a PostgreSQL backup after data loss.")
    parser.add_argument("backup_id", help="Backup ID from the backup manifest list")
    parser.add_argument(
        "--confirmation",
        required=True,
        help="Must be RESTORE:<backup_id>",
    )
    args = parser.parse_args()

    expected_confirmation = f"RESTORE:{args.backup_id}"
    if args.confirmation != expected_confirmation:
        raise SystemExit(f"Invalid confirmation. Expected: {expected_confirmation}")

    service = BackupService()
    record = service.get_backup(args.backup_id)
    dump_path, temp_paths = service._prepare_restore_dump(record)
    try:
        service._verify_backup_integrity(record.manifest, dump_path)
        service._restore_dump(service._build_connection_info(), dump_path)
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    restored_at = datetime.now(UTC).isoformat()
    print(f"Restored backup {args.backup_id} at {restored_at}")


if __name__ == "__main__":
    main()
