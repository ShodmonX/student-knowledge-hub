import json

from app.bootstrap.backup_service import BackupService


if __name__ == "__main__":
    result = BackupService().run_backup()
    print(
        json.dumps(
            {
                "manifest": result.manifest.__dict__,
                "local_deleted": result.local_deleted,
                "offsite_deleted": result.offsite_deleted,
            },
            indent=2,
            sort_keys=True,
        )
    )
