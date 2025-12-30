#!/bin/sh
set -e

# Create necessary directories if they don't exist
mkdir -p /app/database
mkdir -p /app/uploads
mkdir -p /app/audit_storage

# Get port from environment, default to 8000
PORT="${PORT:-8000}"

echo "Starting SphereCast on port $PORT"

# Start the server
exec uvicorn api:app --host 0.0.0.0 --port "$PORT"
