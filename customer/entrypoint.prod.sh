#!/bin/sh
set -e

echo "Starting app in prod mode..."
exec uvicorn app:app \
  --host 0.0.0.0 \
  --port "${API_PORT:-8000}" \
  --workers "${API_WORKERS:-2}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
