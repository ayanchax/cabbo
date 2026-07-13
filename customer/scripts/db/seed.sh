#!/bin/sh
set -eu

ENV_NAME="${1:-local}"
case "$ENV_NAME" in
  local|dev|prod)
    ;;
  *)
    echo "Usage: sh seed.sh [local|dev|prod]" >&2
    exit 1
    ;;
esac

export ENV="$ENV_NAME"

echo "Running seed for ${ENV_NAME}..."
python scripts/seed.py "$ENV_NAME"
echo "Seed finished."

