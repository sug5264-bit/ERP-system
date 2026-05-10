from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.base_model import BaseEntity


class PickStatus(str, PyEnum):
    pending = "pending"
    picking = "picking"
    picked = "picked"
    cancelled = "cancelled"


class ShipmentStatus(str, PyEnum):
    pending = "pending"
    packed = "packed"
    shipped = "shipped"
    delivered = "delivered"
    returned = "returned"


class PickList(BaseEntity):
    """A pick list groups items to be retrieved from stock for one or more
    confirmed sales orders. It tracks who picked what and when."""

    __tablename__ = "wms_pick_lists"

    pick_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey("sales_orders.id"), nullable=False, index=True
    )
    status: Mapped[PickStatus] = mapped_column(
        Enum(PickStatus), default=PickStatus.pending, nullable=False, index=True
    )
    picker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(String(500))

    items: Mapped[list["PickListItem"]] = relationship(
        back_populates="pick_list", cascade="all, delete-orphan"
    )


class PickListItem(BaseEntity):
    __tablename__ = "wms_pick_list_items"

    pick_list_id: Mapped[int] = mapped_column(
        ForeignKey("wms_pick_lists.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    picked_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))
    location: Mapped[str | None] = mapped_column(String(50))

    pick_list: Mapped[PickList] = relationship(back_populates="items")


class Shipment(BaseEntity):
    """One physical package leaving the warehouse. A pick list yields one
    or more shipments."""

    __tablename__ = "wms_shipments"

    shipment_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    pick_list_id: Mapped[int] = mapped_column(
        ForeignKey("wms_pick_lists.id"), nullable=False, index=True
    )
    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey("sales_orders.id"), nullable=False, index=True
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus), default=ShipmentStatus.pending, nullable=False, index=True
    )
    carrier: Mapped[str | None] = mapped_column(String(100))
    tracking_no: Mapped[str | None] = mapped_column(String(100), index=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    packed_at: Mapped[datetime | None] = mapped_column(DateTime)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    address_to: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(500))
