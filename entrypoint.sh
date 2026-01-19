#!/bin/sh
set -e

echo ">>> Waiting for Postgres to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

until PGPASSWORD="${POSTGRES_PASSWORD:-password}" pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" > /dev/null 2>&1; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "!!! Postgres not ready after $MAX_RETRIES attempts. Exiting."
    exit 1
  fi
  echo "Postgres is unavailable - sleeping (attempt $RETRY_COUNT/$MAX_RETRIES)"
  sleep 1
done

echo ">>> Postgres is ready!"

echo ">>> Running Alembic migrations..."
flask db upgrade || {
  echo "!!! Migration failed. Exiting."
  exit 1
}

echo ">>> Starting Gunicorn..."
exec gunicorn --chdir /app wsgi:app -b 0.0.0.0:80 --workers 4 --timeout 120