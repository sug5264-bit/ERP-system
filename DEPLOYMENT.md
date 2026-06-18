# Deployment guide — WELLgreen ERP

Two paths are supported out of the box.

| Option | Audience | Time | HTTPS | Backup |
| ------ | -------- | ---- | ----- | ------ |
| **A** Quick PoC | Internal demo / VPN | ~10 min | no | manual |
| **B** Small-scale ops | Single VM, ~100 users | ~1 hr | auto (Let's Encrypt) | nightly + 14d rotation |

Both share the same images; the production overlay only adds the proxy and
backup containers.

---

## Option A — quick PoC

Single command after generating secrets:

```bash
./scripts/gen-secrets.sh > .env
# (optionally edit .env to set CORS_ORIGINS, SMTP, etc.)

docker compose up -d --build
docker compose logs -f backend   # wait for "alembic ... ok"
```

Endpoints (host network):

- Frontend  http://localhost:3000
- API + Swagger UI  http://localhost:8000/docs
- Healthcheck  http://localhost:8000/api/health/ready

Default seed user: `admin@wellgreen.com` / `admin1234` — **change it immediately
or set `SEED_DEMO_USERS=0` and create your own**.

Stop & wipe:

```bash
docker compose down -v    # -v also deletes the DB volume
```

---

## Option B — small-scale production

### Prerequisites

- A VM with Docker Engine + the Compose plugin (Ubuntu 22.04 LTS works fine).
- A DNS A/AAAA record pointing to the VM (e.g. `erp.example.com`).
- Ports 80 + 443 open inbound.

### Steps

```bash
# 1. Generate secrets
./scripts/gen-secrets.sh > .env

# 2. Fill in the production-only fields
cat >> .env <<'EOF'
ENVIRONMENT=production
PUBLIC_DOMAIN=erp.example.com
LETSENCRYPT_EMAIL=admin@example.com
NEXT_PUBLIC_API_BASE=https://erp.example.com
CORS_ORIGINS=["https://erp.example.com"]
SEED_DEMO_USERS=0
BACKUP_RETENTION_DAYS=14
# Optional: SENTRY_DSN, SLACK_WEBHOOK_URL, SMTP_*, GOOGLE_CLIENT_*
EOF

# 3. Bring everything up
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. Wait for Caddy to issue the certificate (first start can take ~30s)
docker compose logs -f proxy
```

When you see `certificate obtained successfully` the site is live at
`https://erp.example.com`.

### What's running

| Container | Role |
| --------- | ---- |
| `db`       | Postgres 16, ports bound only to the docker network. |
| `backend`  | gunicorn + uvicorn workers (2×4 threads, healthchecked). |
| `frontend` | `next start` production build, non-root, healthchecked. |
| `proxy`    | Caddy — HTTPS termination, auto Let's Encrypt, HSTS. |
| `backup`   | nightly `pg_dump | gzip`, retains last 14 days. |

### Backup & restore

Backups live in the `backup_data` named volume. Copy them off-host:

```bash
# Pull dumps to the host filesystem
docker compose cp backup:/backups ./deploy/backups
```

Restore (downtime required):

```bash
# Bring DB up alone, then restore
docker compose -f docker-compose.yml up -d db
./deploy/restore.sh ./deploy/backups/erp_<timestamp>.sql.gz

# Resume the rest
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Upgrading

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# Alembic runs automatically on backend start.
```

### Rollback

Each git tag is buildable; to revert:

```bash
git checkout v<previous>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# If the schema changed, restore the dump that matches the previous version.
```

---

## Security checklist before going live

- [ ] `JWT_SECRET` ≥ 48 random hex chars (set by `gen-secrets.sh`).
- [ ] `POSTGRES_PASSWORD` ≥ 24 random chars.
- [ ] `SEED_DEMO_USERS=0` (no default admin in production).
- [ ] `CORS_ORIGINS` limited to your real domain(s).
- [ ] `RATE_LIMIT_ENABLED=true`.
- [ ] Backups successfully restored at least once on a staging machine.
- [ ] `SENTRY_DSN` populated so errors are tracked.
- [ ] Slack/email alerts wired for HACCP / approval SLA / cron failures.
- [ ] First admin uses 2FA (`POST /api/auth/2fa/setup` + `/enable`).
