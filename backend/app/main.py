from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings
from app.core.db import Base, engine

# Modules to auto-register. Add a new entry here when introducing a new module.
MODULES = ["auth", "hr", "finance", "inventory", "sales", "audit", "reports"]


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(AuditMiddleware)
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

    @app.get("/api/health")
    def health():
        return {"status": "ok", "modules": MODULES}

    return app


app = create_app()
