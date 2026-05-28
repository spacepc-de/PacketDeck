#!/bin/sh
set -e

if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]; then
  attempts="${DB_MIGRATION_ATTEMPTS:-30}"
  delay="${DB_MIGRATION_RETRY_SECONDS:-2}"
  count=1

  until alembic upgrade head; do
    if [ "$count" -ge "$attempts" ]; then
      echo "Database migrations failed after ${attempts} attempts" >&2
      exit 1
    fi

    echo "Database is not ready for migrations yet; retrying in ${delay}s (${count}/${attempts})" >&2
    count=$((count + 1))
    sleep "$delay"
  done
fi

exec "$@"
