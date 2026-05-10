from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ETaxStatus(str, PyEnum):
    draft = "draft"
    submitted = "submitted"      # sent to Hometax
    accepted = "accepted"        # NTS accepted
    rejected = "rejected"        # NTS rejected
    cancelled = "cancelled"


class ETaxType(str, PyEnum):
    sales = "sales"        # 매출 세금계산서
    purchase = "purchase"  # 매입 세금계산서


class ETaxInvoice(BaseEntity):
    """E-tax invoice (전자세금계산서). Linked to either a billing.Invoice
    (sales) or supplier_invoice (purchase) but stores its own canonical NTS
    fields so it can be re-submitted independently."""

    __tablename__ = "etax_invoices"

    nts_no: Mapped[str | None] = mapped_column(String(100), index=True)  # 국세청승인번호
    type: Mapped[ETaxType] = mapped_column(Enum(ETaxType), nullable=False, index=True)
    status: Mapped[ETaxStatus] = mapped_column(
        Enum(ETaxStatus), default=ETaxStatus.draft, nullable=False, index=True
    )

    # Linkage
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("billing_invoices.id"))
    supplier_invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_supplier_invoices.id")
    )

    # NTS canonical fields
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_business_no: Mapped[str] = mapped_column(String(20), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    buyer_business_no: Mapped[str] = mapped_column(String(20), nullable=False)
    buyer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_summary: Mapped[str] = mapped_column(String(500), nullable=False)  # 품목

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    response_message: Mapped[str | None] = mapped_column(String(2000))
