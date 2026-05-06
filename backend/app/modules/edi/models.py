from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class EDIDirection(str, PyEnum):
    inbound = "inbound"
    outbound = "outbound"


class EDIStatus(str, PyEnum):
    received = "received"
    parsed = "parsed"
    processed = "processed"
    failed = "failed"
    sent = "sent"


class EDIMessageType(str, PyEnum):
    """Subset of common B2B doc types."""
    purchase_order = "PO"           # X12 850 / EDIFACT ORDERS
    order_ack = "ORDRSP"            # X12 855 / EDIFACT ORDRSP
    despatch = "DESADV"             # X12 856 / EDIFACT DESADV
    invoice = "INVOIC"              # X12 810 / EDIFACT INVOIC
    custom = "CUSTOM"


class EDIMessage(BaseEntity):
    __tablename__ = "edi_messages"

    direction: Mapped[EDIDirection] = mapped_column(
        Enum(EDIDirection), nullable=False, index=True
    )
    msg_type: Mapped[EDIMessageType] = mapped_column(
        Enum(EDIMessageType), nullable=False, index=True
    )
    partner_code: Mapped[str | None] = mapped_column(String(50), index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # raw JSON / EDI body
    payload_format: Mapped[str] = mapped_column(String(20), default="json")  # json|x12|edifact
    status: Mapped[EDIStatus] = mapped_column(
        Enum(EDIStatus), default=EDIStatus.received, nullable=False, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    related_resource_type: Mapped[str | None] = mapped_column(String(50))
    related_resource_id: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
