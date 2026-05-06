from datetime import date
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class POStatus(str, PyEnum):
    draft = "draft"
    sent = "sent"          # sent to supplier
    acknowledged = "acknowledged"  # supplier accepted
    shipped = "shipped"    # supplier marked shipped
    received = "received"  # we received it (creates inbound movements)
    cancelled = "cancelled"


class Supplier(BaseEntity):
    __tablename__ = "suppliers"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    business_no: Mapped[str | None] = mapped_column(String(50))  # 사업자등록번호
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    portal_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )  # supplier-portal login account


class PurchaseOrder(BaseEntity):
    __tablename__ = "purchase_orders"

    po_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[POStatus] = mapped_column(
        Enum(POStatus), default=POStatus.draft, nullable=False, index=True
    )
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    supplier: Mapped[Supplier] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(BaseEntity):
    __tablename__ = "purchase_order_items"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    received_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)

    order: Mapped[PurchaseOrder] = relationship(back_populates="items")
