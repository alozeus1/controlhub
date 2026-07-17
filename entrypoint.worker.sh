#!/bin/sh
set -e

echo ">>> Worker: waiting for Postgres..."
RETRY=0
until PGPASSWORD="${POSTGRES_PASSWORD:-password}" pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" > /dev/null 2>&1; do
  RETRY=$((RETRY + 1))
  [ $RETRY -ge 30 ] && { echo "!!! Postgres not ready; exiting."; exit 1; }
  sleep 1
done

# The worker does NOT run migrations (the web/release process owns schema).
echo ">>> Worker: starting RQ worker (queues: ${CAMPAIGN_QUEUE:-campaigns} default)"
exec rq worker --url "${REDIS_URL:-redis://redis:6379/0}" \
  --with-scheduler \
  "${CAMPAIGN_QUEUE:-campaigns}" default
