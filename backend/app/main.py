from datetime import datetime
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings, validate_for_production
from app.core.db import Base, SessionLocal, engine
from app.core.rate_limit import RateLimitMiddleware

MODULES = [
    "auth",
    "hr",
    "finance",
    "inventory",
    "sales",
    "audit",
    "reports",
    "notifications",
    "attachments",
    "approvals",
    "search",
    "currencies",
    "tenants",
    "custom_fields",
    "admin_ops",
    "ledger",
    "ocr",
    "forecast",
]


def _redact(url: str) -> str:
    """Hide password component in DB URLs for the health endpoint."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        return f"{scheme}://{user}:***@{host}"
    return url


def _run_due_schedules() -> None:
    from app.modules.reports.models import ReportSchedule
    from app.modules.reports.service import run_schedule

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due = (
            db.query(ReportSchedule)
            .filter(ReportSchedule.enabled == 1)
            .filter(ReportSchedule.next_run_at <= now)
            .all()
        )
        for s in due:
            try:
                run_schedule(db, s)
            except Exception:
                pass
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    issues = validate_for_production(settings)
    if issues:
        if settings.is_production:
            raise RuntimeError(
                "Refusing to start in production with insecure config:\n  - "
                + "\n  - ".join(issues)
            )
        else:
            for issue in issues:
                print(f"⚠️  config: {issue}")

    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module_name in MODULES:
        import_module(f"app.modules.{module_name}.models")

    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)

    for module_name in MODULES:
        module = import_module(f"app.modules.{module_name}.router")
        app.include_router(module.router)
        if hasattr(module, "ws_router"):
            app.include_router(module.ws_router)

    from app.core.graphql_app import graphql_router
    app.include_router(graphql_router, prefix="/graphql")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "modules": MODULES}

    @app.get("/api/health/detailed")
    def health_detailed():
        from sqlalchemy import text

        result: dict = {
            "status": "ok",
            "environment": settings.environment,
            "modules": MODULES,
            "checks": {},
        }
        try:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                result["checks"]["database"] = {
                    "ok": True,
                    "url": _redact(settings.database_url),
                }
            finally:
                db.close()
        except Exception as exc:
            result["status"] = "degraded"
            result["checks"]["database"] = {"ok": False, "error": str(exc)}

        try:
            db = SessionLocal()
            try:
                row = db.execute(text("SELECT version_num FROM alembic_version")).first()
                result["checks"]["migration"] = {
                    "ok": bool(row),
                    "version": row[0] if row else None,
                }
            finally:
                db.close()
        except Exception as exc:
            result["checks"]["migration"] = {"ok": False, "error": str(exc)}

        result["checks"]["scheduler"] = {"enabled": settings.scheduler_enabled}
        result["checks"]["smtp"] = {"configured": bool(settings.smtp_host)}
        result["checks"]["oauth_google"] = {"configured": bool(settings.google_client_id)}
        return result

    if settings.scheduler_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _run_due_schedules, "interval", minutes=settings.scheduler_interval_minutes
        )

        @app.on_event("startup")
        def _start_scheduler():
            scheduler.start()

        @app.on_event("shutdown")
        def _stop_scheduler():
            scheduler.shutdown(wait=False)

    return app


app = create_app()
