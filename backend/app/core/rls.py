"""Application-level row-level security helpers.

Pattern: managers and admins see all rows; staff/viewer see only rows
they own (`owner_id == user.id`).
"""
from sqlalchemy.orm import Query

from app.core.auth import effective_role


def scope_to_owner(query: Query, model, user, module: str) -> Query:
    """Restrict `query` so that staff/viewer users only see their own records."""
    role = effective_role(user, module)
    if role in ("admin", "manager"):
        return query
    return query.filter(model.owner_id == user.id)


def can_access(record, user, module: str) -> bool:
    role = effective_role(user, module)
    if role in ("admin", "manager"):
        return True
    return getattr(record, "owner_id", None) == user.id
