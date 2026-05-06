from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_role
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogOut

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/logs", response_model=Page[AuditLogOut])
def list_logs(
    params: PageParams = Depends(),
    user_email: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if user_email:
        q = q.filter(AuditLog.user_email.ilike(f"%{user_email}%"))
    if method:
        q = q.filter(AuditLog.method == method.upper())
    if path:
        q = q.filter(AuditLog.path.ilike(f"%{path}%"))
    if status_code is not None:
        q = q.filter(AuditLog.status_code == status_code)
    if since:
        q = q.filter(AuditLog.created_at >= since)
    if until:
        q = q.filter(AuditLog.created_at <= until)
    return paginate(q.order_by(AuditLog.created_at.desc()), params)


@router.get("/logs/export")
def export_logs(format: str = Query("csv"), db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(1000).all()
    headers = ["시간", "사용자", "메서드", "경로", "상태", "IP", "Payload"]
    rows = [
        [
            l.created_at.isoformat(),
            l.user_email or "",
            l.method,
            l.path,
            l.status_code,
            l.ip or "",
            (l.payload or "")[:200],
        ]
        for l in logs
    ]
    return export_table(rows, headers, "audit_logs", format)
