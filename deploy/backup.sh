#!/bin/sh
# Daily Postgres dump with optional offsite sync.
#
# Local rotation (always):
#   /backups/<db>_<ts>.sql.gz   →  BACKUP_RETENTION_DAYS (default 14)
#
# Offsite sync (when BACKUP_REMOTE_TARGET is set — uses rclone, configured
# via the rclone.conf mounted into /config/rclone/rclone.conf):
#   BACKUP_REMOTE_TARGET=myremote:erp-backups
#
# rclone supports AWS S3, GCS, Azure Blob, BackBlaze B2, Synology / QNAP /
# generic SFTP, WebDAV, SMB. Any of these works as the offsite.
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
RETENTION=${BACKUP_RETENTION_DAYS:-14}
REMOTE=${BACKUP_REMOTE_TARGET:-}
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_DIR}/${POSTGRES_DB}_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] dumping to $OUT"
export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_dump --clean --if-exists -U "${POSTGRES_USER}" -h "${PGHOST}" "${POSTGRES_DB}" \
  | gzip -9 > "$OUT"

if [ ! -s "$OUT" ]; then
  echo "ERROR: empty dump" >&2
  rm -f "$OUT"
  exit 1
fi

# Offsite copy (best-effort — local backup still kept if remote fails).
if [ -n "$REMOTE" ]; then
  if command -v rclone >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] syncing to $REMOTE"
    rclone --config /config/rclone/rclone.conf \
           copy "$OUT" "$REMOTE" \
           --s3-storage-class STANDARD_IA 2>&1 || \
      echo "WARNING: rclone copy failed; local backup retained"
  else
    echo "WARNING: BACKUP_REMOTE_TARGET set but rclone not installed; skipping"
  fi
fi

# Local rotation.
find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION}" -delete

echo "[$(date -Iseconds)] backup ok ($(du -h "$OUT" | cut -f1))"
