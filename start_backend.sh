#!/bin/bash
# Start the FastAPI backend server

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✓ Loaded environment variables from .env"
else
    echo "⚠ Warning: .env file not found"
fi

export PYTHONPATH="${PYTHONPATH}:$(pwd)"

echo "Starting SphereCast Backend API..."
echo "API will be available at http://localhost:8000"
echo ""

# Activate virtual environment if it exists
if [ -d .venv ]; then
    source .venv/bin/activate
fi

python3 -m uvicorn api:app --reload --host 0.0.0.0 --port 8000

