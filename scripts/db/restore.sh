#!/bin/sh
set -eu

ENV_NAME="${1:-}"
BACKUP_FILE="${2:-}"
YES="${3:-}"
ENV_FILE=".env.${ENV_NAME}"

if [ -z "$ENV_NAME" ] || [ -z "$BACKUP_FILE" ]; then
  echo "Usage: scripts/db/restore.sh <local|dev|prod> <backup.sql> [--yes]" >&2
  exit 1
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi
if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

read_env() {
  key="$1"
  value="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 | sed -E "s/^[[:space:]]*${key}=//")"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

resolve_ca_file() {
  ca_path="$(read_env DB_SSL_CA || true)"
  if [ -n "$ca_path" ]; then
    case "$ca_path" in
      /*) printf '%s' "$ca_path" ;;
      *) printf '%s/%s' "$(pwd)" "$ca_path" ;;
    esac
    return
  fi

  ca_pem="$(read_env DB_SSL_CA_PEM || true)"
  if [ -n "$ca_pem" ]; then
    temp_ca="${TMPDIR:-/tmp}/cabbo-db-ca-${ENV_NAME}.pem"
    case "$ca_pem" in
      *"-----BEGIN CERTIFICATE-----"*)
        printf '%s\n' "$ca_pem" | sed 's/\\n/\
/g' > "$temp_ca"
        ;;
      *)
        printf '%s' "$ca_pem" | base64 -d > "$temp_ca"
        ;;
    esac
    printf '%s' "$temp_ca"
  fi
}

DB_HOST="$(read_env DB_HOST)"
DB_PORT="$(read_env DB_PORT)"
DB_USER="$(read_env DB_USER)"
DB_PASSWORD="$(read_env DB_PASSWORD)"
DB_NAME="$(read_env DB_NAME)"
CA_FILE="$(resolve_ca_file || true)"

if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ] || [ -z "$DB_NAME" ]; then
  echo "Missing one or more DB_* values in $ENV_FILE" >&2
  exit 1
fi

if [ "$YES" != "--yes" ]; then
  printf "Restore %s into %s database '%s'? Type RESTORE to continue: " "$BACKUP_FILE" "$ENV_NAME" "$DB_NAME"
  read confirmation
  if [ "$confirmation" != "RESTORE" ]; then
    echo "Restore cancelled."
    exit 1
  fi
fi

MYSQL_BIN="$(command -v mysql 2>/dev/null || true)"
if [ -z "$MYSQL_BIN" ]; then
  echo "mysql was not found on this machine." >&2
  echo "Install the MySQL client first, then rerun the restore." >&2
  echo "Examples:" >&2
  echo "  Ubuntu/Debian: sudo apt-get install mariadb-client" >&2
  echo "  macOS: brew install mysql-client" >&2
  echo "  Windows: winget install Oracle.MySQL" >&2
  exit 127
fi

ARGS="--host=${DB_HOST} --port=${DB_PORT} --user=${DB_USER}"
if [ -n "$CA_FILE" ]; then
  ARGS="$ARGS --ssl-ca=${CA_FILE} --ssl-mode=VERIFY_IDENTITY"
fi

echo "Restoring ${BACKUP_FILE} into ${ENV_NAME} database '${DB_NAME}'"
MYSQL_PWD="$DB_PASSWORD" "$MYSQL_BIN" $ARGS "$DB_NAME" < "$BACKUP_FILE"
echo "Restore complete."
