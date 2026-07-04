#!/bin/sh
set -e

echo "Running migrations..."
alembic upgrade head

echo "Running seed..."
python scripts/seed.py

echo "One-off Migration finished."
