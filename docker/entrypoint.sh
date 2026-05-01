#!/bin/sh
set -eu

ensure_runtime_directories() {
  mkdir -p "${STORAGE_ROOT:-/home/appuser/storage}" "${BACKUP_LOCAL_ROOT:-/home/appuser/backups}"
  chown -R appuser:appuser "${STORAGE_ROOT:-/home/appuser/storage}" "${BACKUP_LOCAL_ROOT:-/home/appuser/backups}"
}

if [ "$(id -u)" = "0" ]; then
  ensure_runtime_directories
  exec gosu appuser sh "$0" "$@"
fi

cd /app
export PYTHONPATH="${PYTHONPATH:-/app}"

if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

if [ "${RUN_SEED_ON_START:-true}" = "true" ]; then
  echo "Running seed script..."
  python scripts/seed.py
fi

exec "$@"
