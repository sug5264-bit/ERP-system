from datetime import datetime

from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)
