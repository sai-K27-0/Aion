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
alembic upgrade head
echo "Migrations complete."

# Start the server
echo "Starting Aion backend on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
