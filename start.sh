#!/bin/bash
set -e

# Create necessary directories if they don't exist
mkdir -p /app/database
mkdir -p /app/uploads
mkdir -p /app/audit_storage

# Start the server
exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}

