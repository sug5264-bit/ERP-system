from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"  # development | staging | production
    app_name: str = "WellGreen ERP"
    database_url: str = "sqlite:///./erp.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]
    auto_create_tables: bool = True
    upload_dir: str = "./uploads"
    upload_max_bytes: int = 10 * 1024 * 1024

    # Default-account safety: when True, /scripts/seed.py creates the well-known
    # demo accounts (admin@wellgreen.com / admin1234 etc). Auto-disabled in
    # production unless the operator explicitly opts in.
    seed_demo_users: bool = True

    # Google OAuth (optional)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/oauth/google/callback"
    oauth_default_role: str = "viewer"
    frontend_base: str = "http://localhost:3000"

    # SMTP (optional)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@erp.local"
    smtp_use_tls: bool = True

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 5

    # Observability (optional)
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0  # 0.0 disables performance traces

    # Background task queue (optional)
    celery_broker_url: str | None = None        # e.g. "redis://localhost:6379/0"
    celery_result_backend: str | None = None

    # Slack incoming webhook (optional — multi-channel notifications)
    slack_webhook_url: str | None = None

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 240

    # Observability
    metrics_enabled: bool = True

    # Audit log retention (days). Older entries are auto-purged by scheduler.
    audit_retention_days: int = 365
    ledger_retention_days: int = 0  # 0 = keep forever (chain integrity)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


INSECURE_DEFAULTS = {
    "jwt_secret": ("change-me-in-production",),
}


def validate_for_production(s: Settings) -> list[str]:
    """Return a list of human-readable issues if the config is unsafe for prod."""
    issues: list[str] = []
    if s.jwt_secret in INSECURE_DEFAULTS["jwt_secret"]:
        issues.append("JWT_SECRET is the built-in placeholder. Set a strong random value.")
    if len(s.jwt_secret) < 32:
        issues.append(f"JWT_SECRET is only {len(s.jwt_secret)} chars; use ≥ 32 random bytes.")
    if s.database_url.startswith("sqlite"):
        issues.append("DATABASE_URL points to SQLite. Use Postgres in production.")
    if s.auto_create_tables:
        issues.append("AUTO_CREATE_TABLES=1 in production. Use Alembic migrations instead.")
    if "*" in s.cors_origins:
        issues.append("CORS_ORIGINS contains wildcard '*'. Pin exact origins.")
    if s.seed_demo_users:
        issues.append("SEED_DEMO_USERS=1 in production. Disable to skip well-known accounts.")
    return issues


settings = Settings()
