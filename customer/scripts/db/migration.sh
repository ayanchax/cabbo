#!/bin/sh
set -eu

ENV_NAME="${1:-local}"
case "$ENV_NAME" in
  local|dev|prod)
    ;;
  *)
    echo "Usage: sh migration.sh [local|dev|prod]" >&2
    exit 1
    ;;
esac

export ENV="$ENV_NAME" #Set the ENV variable to the specified environment name, which will be used by the application to determine which environment-specific settings to load.

echo "Running migrations for ${ENV_NAME}..."
alembic upgrade head



echo "Migration finished."
