"""Celery worker config + background tasks.

Activated only when CELERY_BROKER_URL is set. The synchronous in-process
scheduler keeps working when no broker is configured (single-instance ops),
while production deployments swap to: `celery -A app.core.celery_app worker`.

Run a task synchronously (default) or via `.delay()` if broker is up.
"""
from __future__ import annotations

from app.core.config import settings


def get_celery():
    """Returns the Celery app instance, or None if disabled."""
    if not settings.celery_broker_url:
        return None
    try:
        from celery import Celery
    except ImportError:
        return None

    app = Celery(
        "erp",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend or settings.celery_broker_url,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Seoul",
        enable_utc=True,
    )

    # Define tasks lazily inside the function so module import is cheap.
    @app.task(name="erp.send_campaign")
    def send_campaign_task(campaign_id: int):
        from app.core.db import SessionLocal
        from app.modules.crm.router import send_campaign

        db = SessionLocal()
        try:
            return send_campaign(campaign_id, db)
        finally:
            db.close()

    @app.task(name="erp.mrp_run")
    def mrp_run_task(period_code: str):
        from app.core.db import SessionLocal
        from app.modules.manufacturing.router import mrp_run

        db = SessionLocal()
        try:
            return mrp_run(period_code, db)
        finally:
            db.close()

    @app.task(name="erp.escalate_overdue")
    def escalate_overdue_task():
        from app.core.db import SessionLocal
        from app.modules.approvals.router import escalate_overdue

        db = SessionLocal()
        try:
            return escalate_overdue(db)
        finally:
            db.close()

    @app.task(name="erp.run_depreciation")
    def run_depreciation_task(period_code: str):
        from app.core.db import SessionLocal
        from app.modules.assets.router import run_depreciation

        db = SessionLocal()
        try:
            return run_depreciation(period_code, db)
        finally:
            db.close()

    return app


celery_app = get_celery()
