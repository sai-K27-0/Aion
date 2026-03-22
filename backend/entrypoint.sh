#!/bin/bash
set -e

echo "=== Aion Backend Startup ==="

# Validate SECRET_KEY
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "change-this-in-production-to-a-secure-random-key" ]; then
    echo "ERROR: SECRET_KEY is not set or is using the default value."
    echo "The desktop app should generate and pass SECRET_KEY as an environment variable."
    exit 1
fi

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
while ! pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-aion}" -q 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

# Run database migrations
echo "Running database migrations..."
# If alembic has no version stamped but tables exist, stamp to head first
CURRENT=$(alembic current 2>/dev/null | grep -c "head" || true)
if [ "$CURRENT" = "0" ]; then
    # Check if tables already exist (pre-alembic setup)
    TABLE_EXISTS=$(PGPASSWORD="${POSTGRES_PASSWORD:-aion_local_secret}" psql -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER:-aion}" -d "${POSTGRES_DB:-aion}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='users'" 2>/dev/null | tr -d ' ' || echo "0")
    if [ "$TABLE_EXISTS" != "0" ] && [ "$TABLE_EXISTS" != "" ]; then
        echo "Existing database detected. Stamping alembic to head..."
        alembic stamp head
    fi
fi
alembic upgrade head || echo "WARNING: Migration failed, continuing anyway..."
echo "Migrations complete."

# Start the server
echo "Starting Aion backend on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
