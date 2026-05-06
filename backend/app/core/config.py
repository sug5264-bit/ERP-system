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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
