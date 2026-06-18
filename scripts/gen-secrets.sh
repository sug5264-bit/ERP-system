#!/usr/bin/env bash
# Generate strong secrets and print a ready-to-paste .env snippet.
# Usage:  ./scripts/gen-secrets.sh > .env  (or append to existing)
set -euo pipefail

rand_hex() { python3 -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"; }
rand_urlsafe() { python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$1"; }

cat <<EOF
# Generated $(date -Iseconds) — keep this file out of git.

POSTGRES_USER=erp
POSTGRES_PASSWORD=$(rand_urlsafe 24)
POSTGRES_DB=erp

JWT_SECRET=$(rand_hex 48)
ENVIRONMENT=production
SEED_DEMO_USERS=0
AUTO_CREATE_TABLES=0
RATE_LIMIT_ENABLED=true
SCHEDULER_ENABLED=true
EOF
