"""Quote → Invoice → Payment.

A Quote is a draft proposal that becomes a SalesOrder when converted.
An Invoice is generated from a confirmed SalesOrder (or directly).
A Payment is recorded against one or more invoices.
"""
from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class QuoteStatus(str, PyEnum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class InvoiceStatus(str, PyEnum):
    draft = "draft"
    issued = "issued"
    partially_paid = "partially_paid"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


class Quote(BaseEntity):
    __tablename__ = "billing_quotes"

    quote_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("sales_customers.id"), nullable=False, index=True
    )
    issued_date: Mapped[date] = mapped_column(Date, default=date.today)
    expires_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), default=QuoteStatus.draft, nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(String(1000))
    converted_order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"))

    items: Mapped[list["QuoteItem"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteItem(BaseEntity):
    __tablename__ = "billing_quote_items"

    quote_id: Mapped[int] = mapped_column(
        ForeignKey("billing_quotes.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    quote: Mapped[Quote] = relationship(back_populates="items")


class Invoice(BaseEntity):
    __tablename__ = "billing_invoices"

    invoice_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("sales_customers.id"), nullable=False, index=True
    )
    sales_order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"))
    issued_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus), default=InvoiceStatus.draft, nullable=False, index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(String(1000))

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceItem(BaseEntity):
    __tablename__ = "billing_invoice_items"

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("billing_invoices.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("inv_items.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Payment(BaseEntity):
    __tablename__ = "billing_payments"

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("billing_invoices.id"), nullable=False, index=True
    )
    paid_at: Mapped[date] = mapped_column(Date, default=date.today)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="bank_transfer")
    reference: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(500))
