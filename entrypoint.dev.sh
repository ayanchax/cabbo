#!/bin/sh
set -e

echo "Starting app in dev mode..."
exec uvicorn app:app --host 0.0.0.0 --port "${API_PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
