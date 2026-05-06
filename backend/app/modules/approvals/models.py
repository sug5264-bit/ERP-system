from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class ApprovalStatus(str, PyEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ApprovalFormTemplate(BaseEntity):
    """A reusable approval form definition.

    `schema` is a JSON-encoded list of fields:
        [{key, label, type: text|number|date|select|textarea, required, options}]

    `default_steps` is optional — list of {order, approver_id} used to
    pre-populate the approval chain when the template is selected.
    """

    __tablename__ = "approval_form_templates"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    schema: Mapped[str] = mapped_column(String(8000), default="[]")
    default_steps: Mapped[str] = mapped_column(String(2000), default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


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

    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_form_templates.id"), index=True
    )
    form_data: Mapped[str | None] = mapped_column(String(8000))  # JSON-encoded answers

    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.order",
    )
    template: Mapped[ApprovalFormTemplate | None] = relationship()


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
