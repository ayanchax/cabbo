#!/bin/sh
set -eu

ENV_NAME="${1:-local}"
OUT_DIR="${2:-backups/db}"
ENV_FILE=".env.${ENV_NAME}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Environment file not found: $ENV_FILE" >&2
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

mkdir -p "$OUT_DIR"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${OUT_DIR}/${ENV_NAME}-${DB_NAME}-${TIMESTAMP}.sql"

MYSQLDUMP_BIN="$(command -v mysqldump 2>/dev/null || true)"
if [ -z "$MYSQLDUMP_BIN" ]; then
  echo "mysqldump was not found on this machine." >&2
  echo "Install the MySQL client first, then rerun the backup." >&2
  echo "Examples:" >&2
  echo "  Ubuntu/Debian: sudo apt-get install mariadb-client" >&2
  echo "  macOS: brew install mysql-client" >&2
  echo "  Windows: winget install Oracle.MySQL" >&2
  exit 127
fi

ARGS="--host=${DB_HOST} --port=${DB_PORT} --user=${DB_USER} --single-transaction --quick --routines --triggers --events --set-gtid-purged=OFF"
if [ -n "$CA_FILE" ]; then
  ARGS="$ARGS --ssl-ca=${CA_FILE} --ssl-mode=VERIFY_IDENTITY"
fi

echo "Creating ${ENV_NAME} DB backup at ${BACKUP_FILE}"
MYSQL_PWD="$DB_PASSWORD" "$MYSQLDUMP_BIN" $ARGS "$DB_NAME" > "$BACKUP_FILE"
echo "Backup complete: ${BACKUP_FILE}"
