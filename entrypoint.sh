#!/bin/sh

echo "🔄 Running migrations..."
alembic upgrade head

echo "🌱 Running seed..."
python scripts/seed.py

echo "🚀 Starting app..."
uvicorn app:app --host 0.0.0.0 --port 8000