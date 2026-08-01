#!/bin/sh
set -eu

ENV_NAME="${1:-local}"
case "$ENV_NAME" in
  local|dev|prod)
    shift || true
    ;;
  *)
    echo "Usage: sh bulk_onboard_drivers.sh [local|dev|prod] [--execute] [--file path]" >&2
    exit 1
    ;;
esac

export ENV="$ENV_NAME"

echo "Running bulk driver onboarding for ${ENV_NAME}..."
python scripts/bulk_onboard_drivers.py "$ENV_NAME" "$@"
echo "Bulk driver onboarding finished."
