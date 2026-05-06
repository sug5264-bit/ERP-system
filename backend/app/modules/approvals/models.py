from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class ApprovalStatus(str, PyEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ApprovalRequest(BaseEntity):
    """Generic approval request — links to any module record via (resource_type, resource_id)."""

    __tablename__ = "approval_requests"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.order",
    )


class ApprovalStep(BaseEntity):
    __tablename__ = "approval_steps"

    request_id: Mapped[int] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False
    )
    comment: Mapped[str | None] = mapped_column(String(1000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    request: Mapped[ApprovalRequest] = relationship(back_populates="steps")
