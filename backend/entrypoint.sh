#!/bin/bash

set -e

# Initialize database
echo "Initializing database..."
python -c "from app.db import init_db; init_db()"

# Check if we should start the worker or API server
if [ "$WORKER_MODE" = "true" ]; then
    echo "Starting background worker..."
    python -m app.core.worker
else
    echo "Starting FastAPI server..."
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
