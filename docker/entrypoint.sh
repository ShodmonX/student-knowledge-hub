#!/bin/sh
set -eu

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
