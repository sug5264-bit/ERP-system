"""Quote-to-Cash endpoints (manager+ for write, admin for state changes)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.billing.models import (
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Payment,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from app.modules.sales.models import (
    Customer,
    OrderStatus,
    SalesOrder,
    SalesOrderItem,
)

router = APIRouter(
    prefix="/api/billing",
    tags=["billing"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class QuoteLineIn(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal


class QuoteLineOut(QuoteLineIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class QuoteIn(BaseModel):
    quote_no: str
    customer_id: int
    expires_date: date | None = None
    notes: str | None = None
    items: list[QuoteLineIn] = Field(min_length=1)


class QuoteOut(BaseModel):
    id: int
    quote_no: str
    customer_id: int
    issued_date: date
    expires_date: date | None
    status: QuoteStatus
    total: Decimal
    notes: str | None
    converted_order_id: int | None
    items: list[QuoteLineOut]
    model_config = ConfigDict(from_attributes=True)


class InvoiceLineIn(BaseModel):
    description: str
    item_id: int | None = None
    quantity: Decimal
    unit_price: Decimal


class InvoiceLineOut(InvoiceLineIn):
    id: int
    line_total: Decimal
    model_config = ConfigDict(from_attributes=True)


class InvoiceIn(BaseModel):
    invoice_no: str
    customer_id: int
    sales_order_id: int | None = None
    due_date: date | None = None
    notes: str | None = None
    tax_rate: Decimal = Decimal("0.10")  # default 10% VAT
    items: list[InvoiceLineIn] = Field(min_length=1)


class InvoiceOut(BaseModel):
    id: int
    invoice_no: str
    customer_id: int
    sales_order_id: int | None
    issued_date: date
    due_date: date | None
    status: InvoiceStatus
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    paid_amount: Decimal
    notes: str | None
    items: list[InvoiceLineOut]
    model_config = ConfigDict(from_attributes=True)


class PaymentIn(BaseModel):
    invoice_id: int
    amount: Decimal
    paid_at: date | None = None
    method: str = "bank_transfer"
    reference: str | None = None
    notes: str | None = None


class PaymentOut(BaseModel):
    id: int
    invoice_id: int
    paid_at: date
    amount: Decimal
    method: str
    reference: str | None
    notes: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- Quotes ---------------------------------------------------------------


@router.get("/quotes", response_model=Page[QuoteOut])
def list_quotes(params: PageParams = Depends(), db: Session = Depends(get_db)):
    q = (
        db.query(Quote)
        .options(selectinload(Quote.items))
        .order_by(Quote.issued_date.desc())
    )
    return paginate(q, params)


@router.post(
    "/quotes",
    response_model=QuoteOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_quote(payload: QuoteIn, db: Session = Depends(get_db)):
    if not db.query(Customer).filter(Customer.id == payload.customer_id).first():
        raise HTTPException(status_code=404, detail="Customer not found")
    if db.query(Quote).filter(Quote.quote_no == payload.quote_no).first():
        raise HTTPException(status_code=400, detail="Quote no already exists")
    total = sum(
        (Decimal(l.quantity) * Decimal(l.unit_price) for l in payload.items),
        Decimal("0"),
    )
    q = Quote(
        quote_no=payload.quote_no,
        customer_id=payload.customer_id,
        expires_date=payload.expires_date,
        notes=payload.notes,
        total=total,
    )
    for line in payload.items:
        q.items.append(QuoteItem(**line.model_dump()))
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


@router.post(
    "/quotes/{quote_id}/convert",
    response_model=dict,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def convert_quote_to_order(quote_id: int, db: Session = Depends(get_db)):
    """Accepted quote → new SalesOrder. Quote becomes 'accepted' and links the order."""
    q = (
        db.query(Quote)
        .options(selectinload(Quote.items))
        .filter(Quote.id == quote_id)
        .with_for_update()
        .first()
    )
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    if q.converted_order_id:
        raise HTTPException(status_code=400, detail="Already converted")
    if q.status not in (QuoteStatus.draft, QuoteStatus.sent, QuoteStatus.accepted):
        raise HTTPException(
            status_code=400, detail=f"Cannot convert {q.status.value} quote"
        )

    order = SalesOrder(
        order_no=f"SO-FROM-{q.quote_no}",
        customer_id=q.customer_id,
        order_date=date.today(),
        status=OrderStatus.draft,
        total=q.total,
    )
    for line in q.items:
        order.items.append(
            SalesOrderItem(
                item_id=line.item_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        )
    db.add(order)
    db.flush()
    q.converted_order_id = order.id
    q.status = QuoteStatus.accepted
    db.commit()
    return {"order_id": order.id, "order_no": order.order_no, "quote_id": q.id}


# ---- Invoices --------------------------------------------------------------


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(params: PageParams = Depends(), db: Session = Depends(get_db)):
    q = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.issued_date.desc())
    )
    return paginate(q, params)


@router.post(
    "/invoices",
    response_model=InvoiceOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def create_invoice(payload: InvoiceIn, db: Session = Depends(get_db)):
    if db.query(Invoice).filter(Invoice.invoice_no == payload.invoice_no).first():
        raise HTTPException(status_code=400, detail="Invoice no already exists")
    if not db.query(Customer).filter(Customer.id == payload.customer_id).first():
        raise HTTPException(status_code=404, detail="Customer not found")

    subtotal = Decimal("0")
    inv = Invoice(
        invoice_no=payload.invoice_no,
        customer_id=payload.customer_id,
        sales_order_id=payload.sales_order_id,
        due_date=payload.due_date,
        notes=payload.notes,
        status=InvoiceStatus.draft,
    )
    for line in payload.items:
        line_total = Decimal(line.quantity) * Decimal(line.unit_price)
        subtotal += line_total
        inv.items.append(
            InvoiceItem(
                description=line.description,
                item_id=line.item_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line_total,
            )
        )
    inv.subtotal = subtotal
    inv.tax = (subtotal * payload.tax_rate).quantize(Decimal("0.01"))
    inv.total = inv.subtotal + inv.tax
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/invoices/{invoice_id}/issue",
    response_model=InvoiceOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def issue_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != InvoiceStatus.draft:
        raise HTTPException(status_code=400, detail=f"Can only issue draft (got {inv.status.value})")
    inv.status = InvoiceStatus.issued
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/invoices/{invoice_id}/cancel",
    response_model=InvoiceOut,
    dependencies=[Depends(require_role("admin"))],
)
def cancel_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if Decimal(inv.paid_amount) > 0:
        raise HTTPException(status_code=400, detail="Cannot cancel invoice with payments")
    inv.status = InvoiceStatus.cancelled
    db.commit()
    db.refresh(inv)
    return inv


# ---- Payments --------------------------------------------------------------


@router.get("/payments", response_model=Page[PaymentOut])
def list_payments(
    invoice_id: int | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Payment).order_by(Payment.paid_at.desc())
    if invoice_id is not None:
        q = q.filter(Payment.invoice_id == invoice_id)
    return paginate(q, params)


@router.post(
    "/payments",
    response_model=PaymentOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def record_payment(payload: PaymentIn, db: Session = Depends(get_db)):
    inv = (
        db.query(Invoice)
        .filter(Invoice.id == payload.invoice_id)
        .with_for_update()
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status in (InvoiceStatus.cancelled, InvoiceStatus.draft):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pay invoice in {inv.status.value} state — issue it first",
        )
    new_paid = Decimal(inv.paid_amount) + Decimal(payload.amount)
    if new_paid > Decimal(inv.total):
        raise HTTPException(
            status_code=400,
            detail=f"Overpayment: {new_paid} > total {inv.total}",
        )
    p = Payment(
        invoice_id=inv.id,
        amount=payload.amount,
        paid_at=payload.paid_at or date.today(),
        method=payload.method,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(p)
    inv.paid_amount = new_paid
    inv.status = (
        InvoiceStatus.paid if new_paid == Decimal(inv.total) else InvoiceStatus.partially_paid
    )
    db.commit()
    db.refresh(p)
    return p
