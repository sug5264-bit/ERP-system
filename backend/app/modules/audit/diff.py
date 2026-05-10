"""Helper to record before/after diffs into the audit log.

Service code calls `record_update(db, resource_type, resource_id, before, after, user_id)`
after applying a change. The middleware-based audit row gets enriched with the
field-level diff so admins can see exactly what changed.
"""
import json
from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog


def diff_dicts(before: dict, after: dict) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    keys = set(before) | set(after)
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            out[k] = {"before": b, "after": a}
    return out


def record_update(
    db: Session,
    *,
    resource_type: str,
    resource_id: int,
    before: dict,
    after: dict,
    user_id: int | None = None,
    user_email: str | None = None,
    path: str = "",
    method: str = "PATCH",
) -> AuditLog | None:
    d = diff_dicts(before, after)
    if not d:
        return None
    row = AuditLog(
        user_id=user_id,
        user_email=user_email,
        method=method,
        path=path,
        status_code=200,
        payload=None,
        diff=json.dumps(d, ensure_ascii=False, default=str),
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def snapshot(obj, fields: list[str]) -> dict:
    """Capture the listed attributes of an ORM object into a plain dict."""
    return {f: getattr(obj, f, None) for f in fields}
