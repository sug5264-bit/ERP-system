from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: int
    related_type: str | None
    related_id: int | None
    filename: str
    content_type: str
    size: int
    uploaded_by: int | None
    created_at: datetime

    class Config:
        from_attributes = True
