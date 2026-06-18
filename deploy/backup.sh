#!/bin/sh
# Daily Postgres dump with rotation. Run from the `backup` compose service.
#
# Env vars: PGHOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
#           BACKUP_RETENTION_DAYS (default 14).
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
RETENTION=${BACKUP_RETENTION_DAYS:-14}
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_DIR}/${POSTGRES_DB}_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] backing up to $OUT"
export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_dump --clean --if-exists -U "${POSTGRES_USER}" -h "${PGHOST}" "${POSTGRES_DB}" \
  | gzip -9 > "$OUT"

# Verify the dump is non-empty.
if [ ! -s "$OUT" ]; then
  echo "ERROR: backup file is empty" >&2
  rm -f "$OUT"
  exit 1
fi

# Rotate: drop dumps older than RETENTION days.
find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION}" -delete

echo "[$(date -Iseconds)] backup ok ($(du -h "$OUT" | cut -f1))"
