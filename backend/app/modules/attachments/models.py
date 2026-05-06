from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class Attachment(BaseEntity):
    """Generic attachment, optionally linked to any module record via (related_type, related_id)."""

    __tablename__ = "attachments"

    related_type: Mapped[str | None] = mapped_column(String(50), index=True)
    related_id: Mapped[int | None] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
