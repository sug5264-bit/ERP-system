from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ERP System"
    database_url: str = "sqlite:///./erp.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: list[str] = ["http://localhost:3000"]
    auto_create_tables: bool = True  # PoC default; set False when using Alembic in prod
    upload_dir: str = "./uploads"
    upload_max_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Google OAuth (optional)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/oauth/google/callback"
    oauth_default_role: str = "viewer"  # role assigned to first-time SSO users
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
