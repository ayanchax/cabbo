#!/bin/sh
set -e

echo "Starting app in local mode..."
exec uvicorn app:app --host 0.0.0.0 --port "${API_PORT:-8000}" --reload
