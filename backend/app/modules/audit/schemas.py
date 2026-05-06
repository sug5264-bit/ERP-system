from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None
    method: str
    path: str
    status_code: int
    ip: str | None
    payload: str | None
    created_at: datetime

    class Config:
        from_attributes = True
