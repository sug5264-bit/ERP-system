#!/bin/sh
# Restore a Postgres dump produced by deploy/backup.sh.
#
# Usage (run from the project root, after `docker compose up -d db`):
#   ./deploy/restore.sh deploy/backups/erp_20260513T000000Z.sql.gz
set -eu

DUMP="${1:?usage: restore.sh path/to/dump.sql.gz}"
USER=${POSTGRES_USER:-erp}
DB=${POSTGRES_DB:-erp}
HOST=${PGHOST:-localhost}

if [ ! -f "$DUMP" ]; then
  echo "Dump not found: $DUMP" >&2
  exit 1
fi

printf "About to restore %s into %s@%s. Type YES to continue: " "$DUMP" "$DB" "$HOST"
read confirm
[ "$confirm" = "YES" ] || { echo "Aborted."; exit 1; }

gunzip -c "$DUMP" | PGPASSWORD="${POSTGRES_PASSWORD}" \
  psql -U "$USER" -h "$HOST" -d "$DB"

echo "Restore complete."
