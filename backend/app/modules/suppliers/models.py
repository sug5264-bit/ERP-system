from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
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
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    received_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))

    order: Mapped[PurchaseOrder] = relationship(back_populates="items")


class GRStatus(str, PyEnum):
    draft = "draft"
    posted = "posted"


class GoodsReceipt(BaseEntity):
    """A receipt of physical goods against a PO. One PO can have many GRs
    (partial receipts). Posting a GR generates inbound stock movements and
    bumps the matching PO line's received_qty."""

    __tablename__ = "purchase_goods_receipts"

    gr_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    po_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    received_date: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[GRStatus] = mapped_column(
        Enum(GRStatus), default=GRStatus.draft, nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(1000))
    posted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        back_populates="gr", cascade="all, delete-orphan"
    )


class GoodsReceiptItem(BaseEntity):
    __tablename__ = "purchase_goods_receipt_items"

    gr_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_goods_receipts.id"), nullable=False, index=True
    )
    po_item_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_items.id"), nullable=False
    )
    received_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))

    gr: Mapped[GoodsReceipt] = relationship(back_populates="items")


class SupplierInvoiceStatus(str, PyEnum):
    pending = "pending"
    matched = "matched"  # 3-way match passed
    rejected = "rejected"  # mismatch — manual review
    paid = "paid"


class SupplierInvoice(BaseEntity):
    """Vendor's invoice. Required for 3-way matching: PO ↔ GR ↔ Invoice."""

    __tablename__ = "purchase_supplier_invoices"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "vendor_invoice_no", name="uq_supplier_invoice_no"
        ),
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    po_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    vendor_invoice_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[SupplierInvoiceStatus] = mapped_column(
        Enum(SupplierInvoiceStatus),
        default=SupplierInvoiceStatus.pending,
        nullable=False,
        index=True,
    )
    match_notes: Mapped[str | None] = mapped_column(String(1000))
