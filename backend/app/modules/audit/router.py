from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_role
from app.core.db import get_db
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogOut

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/logs", response_model=list[AuditLogOut])
def list_logs(
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
