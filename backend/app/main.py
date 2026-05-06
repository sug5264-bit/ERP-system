from datetime import datetime
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.rate_limit import RateLimitMiddleware

# Modules to auto-register. Add a new entry here when introducing a new module.
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

    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import all module models so SQLAlchemy is aware of them
    for module_name in MODULES:
        import_module(f"app.modules.{module_name}.models")

    # Auto-create tables only when AUTO_CREATE_TABLES=1 (PoC dev mode).
    # In production, use Alembic migrations instead.
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)

    for module_name in MODULES:
        module = import_module(f"app.modules.{module_name}.router")
        app.include_router(module.router)
        if hasattr(module, "ws_router"):
            app.include_router(module.ws_router)

    # GraphQL gateway (read-only)
    from app.core.graphql_app import graphql_router
    app.include_router(graphql_router, prefix="/graphql")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "modules": MODULES}

    if settings.scheduler_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_due_schedules, "interval", minutes=settings.scheduler_interval_minutes)

        @app.on_event("startup")
        def _start_scheduler():
            scheduler.start()

        @app.on_event("shutdown")
        def _stop_scheduler():
            scheduler.shutdown(wait=False)

    return app


app = create_app()
