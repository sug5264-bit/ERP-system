from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class DSRType(str, PyEnum):
    access = "access"            # 열람
    erasure = "erasure"          # 삭제
    portability = "portability"  # 이동
    correction = "correction"    # 정정


class DSRStatus(str, PyEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"


class DataSubjectRequest(BaseEntity):
    """A privacy request from a data subject. Required by GDPR Art. 15-22 and
    Korean PIPA Art. 35-37."""

    __tablename__ = "privacy_dsr"

    type: Mapped[DSRType] = mapped_column(Enum(DSRType), nullable=False, index=True)
    subject_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[DSRStatus] = mapped_column(
        Enum(DSRStatus), default=DSRStatus.pending, nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Per Korean PIPA: response within 10 days (extendable to 30 with notice)
    due_at: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    response_notes: Mapped[str | None] = mapped_column(String(4000))


class RetentionPolicy(BaseEntity):
    """Data retention rules. After `retain_days` past creation, records of
    `resource_type` may be purged or anonymized by the cleanup job."""

    __tablename__ = "privacy_retention_policies"

    resource_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    retain_days: Mapped[int] = mapped_column(default=2555)  # 7 years default
    action: Mapped[str] = mapped_column(String(20), default="anonymize")  # anonymize|purge
    notes: Mapped[str | None] = mapped_column(String(500))
