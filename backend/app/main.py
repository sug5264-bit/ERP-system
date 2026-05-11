from app.core.time import utc_now
from datetime import datetime
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings, validate_for_production
from app.core.db import Base, SessionLocal, engine
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.request_id import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

configure_logging()

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
    "suppliers",
    "edi",
    "billing",
    "manufacturing",
    "report_builder",
    "assets",
    "crm",
    "etax",
    "projects",
    "fx",
    "dashboards",
    "privacy",
    "wms",
    "ats",
    "kpi",
    "consolidation",
    "ai_posting",
    "qc",
    "compliance",
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


def _purge_expired_audit_logs() -> None:
    """Drop audit_logs older than `audit_retention_days`."""
    if settings.audit_retention_days <= 0:
        return
    from datetime import timedelta

    from app.modules.audit.models import AuditLog

    cutoff = utc_now() - timedelta(days=settings.audit_retention_days)
    db = SessionLocal()
    try:
        deleted = (
            db.query(AuditLog)
            .filter(AuditLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            import logging

            logging.getLogger("erp.audit").info("purged %s old audit rows", deleted)
    finally:
        db.close()


def _run_due_schedules() -> None:
    from app.modules.reports.models import ReportSchedule
    from app.modules.reports.service import run_schedule

    db = SessionLocal()
    try:
        now = utc_now()
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


def _init_sentry() -> None:
    """Wire Sentry SDK if a DSN is configured. Silently skips otherwise."""
    dsn = getattr(settings, "sentry_dsn", None)
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment,
            traces_sample_rate=getattr(settings, "sentry_traces_sample_rate", 0.0),
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
    except ImportError:
        # sentry_sdk not installed — production should pin it in requirements.
        pass


def create_app() -> FastAPI:
    _init_sentry()
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

    install_exception_handlers(app)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
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

    if settings.metrics_enabled:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            Instrumentator(
                excluded_handlers=["/api/health.*", "/metrics"]
            ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
        except ImportError:
            pass

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
        result["checks"]["sentry"] = {
            "configured": bool(getattr(settings, "sentry_dsn", None))
        }
        result["checks"]["celery"] = {
            "configured": bool(getattr(settings, "celery_broker_url", None))
        }
        return result

    @app.get("/api/health/live")
    def health_live():
        """Liveness probe — just process is up. No external dependencies."""
        return {"status": "ok"}

    @app.get("/api/health/ready")
    def health_ready():
        """Readiness probe — DB reachable + migration applied. Returns 503
        if any dependency is down so Kubernetes/Cloud Run can stop routing
        traffic until recovery."""
        from fastapi import Response
        from sqlalchemy import text

        try:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                row = db.execute(text("SELECT version_num FROM alembic_version")).first()
                if not row:
                    return Response(
                        content='{"ready": false, "reason": "no migration"}',
                        status_code=503, media_type="application/json",
                    )
            finally:
                db.close()
        except Exception as exc:
            return Response(
                content=f'{{"ready": false, "reason": "db: {exc}"}}',
                status_code=503, media_type="application/json",
            )
        return {"ready": True}

    if settings.scheduler_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _run_due_schedules, "interval", minutes=settings.scheduler_interval_minutes
        )
        # Daily audit log retention sweep
        scheduler.add_job(_purge_expired_audit_logs, "interval", hours=24)

        @app.on_event("startup")
        def _start_scheduler():
            scheduler.start()

        @app.on_event("shutdown")
        def _stop_scheduler():
            scheduler.shutdown(wait=False)

    return app


app = create_app()
