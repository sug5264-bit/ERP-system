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


# ---- Quote PDF -------------------------------------------------------------


def _customer_to_party(cust: Customer):
    from app.core.docs_pdf import PartyInfo

    return PartyInfo(
        business_no=cust.business_no,
        company_name=cust.company or cust.name,
        representative=cust.representative,
        address=cust.address,
        business_type=cust.business_type,
        business_item=cust.business_item,
        phone=cust.phone,
        fax=cust.fax,
    )


def _company_party_or_400(db: Session, tenant_id: int | None = None):
    from app.core.docs_pdf import PartyInfo
    from app.modules.company.router import get_company_profile

    cp = get_company_profile(db, tenant_id)
    if not cp:
        raise HTTPException(
            status_code=400,
            detail="회사정보가 등록되어 있지 않습니다. PUT /api/company-profile 로 등록하세요.",
        )
    party = PartyInfo(
        business_no=cp.business_no,
        company_name=cp.company_name,
        representative=cp.representative,
        address=cp.address,
        business_type=cp.business_type,
        business_item=cp.business_item,
        phone=cp.phone,
        fax=cp.fax,
    )
    return party, cp


def _pdf_response(pdf_bytes: bytes, filename: str):
    import io as _io

    from fastapi.responses import StreamingResponse

    from app.core.exports import _content_disposition

    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename, inline=True)},
    )


@router.get("/quotes/{quote_id}/quote.pdf")
def quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    """견적서 PDF."""
    from app.core.docs_pdf import LineItem, render_quote
    from app.modules.inventory.models import Item

    q = (
        db.query(Quote)
        .options(selectinload(Quote.items))
        .filter(Quote.id == quote_id)
        .first()
    )
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    cust = db.query(Customer).filter(Customer.id == q.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    company, _ = _company_party_or_400(db)
    customer = _customer_to_party(cust)

    item_ids = [li.item_id for li in q.items]
    items_by_id = {i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()}
    vat = Decimal("0.10")
    lines: list = []
    for idx, li in enumerate(q.items, start=1):
        prod = items_by_id.get(li.item_id)
        if not prod:
            continue
        supply = (Decimal(li.quantity) * Decimal(li.unit_price)).quantize(Decimal("1"))
        tax = (supply * vat).quantize(Decimal("1"))
        lines.append(
            LineItem(
                no=idx,
                name=prod.name,
                spec=prod.sku,
                qty=Decimal(li.quantity),
                unit=prod.unit or "EA",
                unit_price=Decimal(li.unit_price),
                supply_amount=supply,
                tax_amount=tax,
            )
        )

    pdf = render_quote(
        company,
        customer,
        lines,
        doc_no=q.quote_no,
        doc_date=q.issued_date,
        expires_date=q.expires_date,
        notes=q.notes,
    )
    return _pdf_response(pdf, f"견적서_{q.quote_no}.pdf")


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
    # Auto-post: Dr AR / Cr Revenue + VAT
    try:
        from app.modules.finance.auto_post import post_invoice_issued

        post_invoice_issued(db, inv)
    except Exception:
        import logging
        logging.getLogger("erp.billing").exception(
            "auto-post failed for invoice %s — invoice still issued", inv.invoice_no
        )
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/invoices/{invoice_id}/cancel",
    response_model=InvoiceOut,
    dependencies=[Depends(require_role("admin"))],
)
def cancel_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )
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
    db.flush()  # so payment.id is available for the auto-post reference
    # Auto-post: Dr Cash / Cr AR
    try:
        from app.modules.finance.auto_post import post_payment_received

        post_payment_received(db, p)
    except Exception:
        import logging
        logging.getLogger("erp.billing").exception(
            "auto-post failed for payment %s — payment still recorded", p.id
        )
    db.commit()
    db.refresh(p)
    return p


# ---- Tax Invoice / Customer Ledger PDFs -----------------------------------


@router.get("/invoices/{invoice_id}/tax-invoice.pdf")
def tax_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    """세금계산서 PDF (국세청 양식 준용)."""
    from app.core.docs_pdf import LineItem, render_tax_invoice
    from app.modules.inventory.models import Item

    inv = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    company, cp = _company_party_or_400(db)
    customer = _customer_to_party(cust)

    # 세금계산서는 invoice subtotal/tax를 사용. 라인별 분배.
    total_supply = Decimal(inv.subtotal)
    total_tax = Decimal(inv.tax)
    lines: list = []
    item_ids = [li.item_id for li in inv.items if li.item_id]
    items_by_id = (
        {i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()}
        if item_ids
        else {}
    )
    for idx, li in enumerate(inv.items, start=1):
        prod = items_by_id.get(li.item_id) if li.item_id else None
        supply = Decimal(li.line_total)
        tax_line = (
            (supply / total_supply * total_tax).quantize(Decimal("1"))
            if total_supply > 0
            else Decimal(0)
        )
        lines.append(
            LineItem(
                no=idx,
                name=li.description,
                spec=(prod.sku if prod else None),
                qty=Decimal(li.quantity),
                unit=(prod.unit if prod else "EA"),
                unit_price=Decimal(li.unit_price),
                supply_amount=supply,
                tax_amount=tax_line,
            )
        )

    bank_info = None
    if cp.bank_name and cp.bank_account:
        bank_info = f"{cp.bank_name} {cp.bank_account}" + (
            f" (예금주: {cp.bank_holder})" if cp.bank_holder else ""
        )
    pdf = render_tax_invoice(
        company,
        customer,
        lines,
        doc_no=inv.invoice_no,
        doc_date=inv.issued_date,
        is_exempt=(total_tax == 0),
        bank_info=bank_info,
    )
    return _pdf_response(pdf, f"세금계산서_{inv.invoice_no}.pdf")


@router.get("/customers/{customer_id}/ledger.pdf")
def customer_ledger_pdf(
    customer_id: int,
    period_from: date,
    period_to: date,
    db: Session = Depends(get_db),
):
    """거래원장 PDF — 거래처 기준 매출/입금/잔액 시계열."""
    from app.core.docs_pdf import LedgerRow, render_customer_ledger

    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    company, _ = _company_party_or_400(db)
    customer = _customer_to_party(cust)

    # 기초잔액 = 기간 시작 이전 (매출 - 입금)
    opening_q = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.issued_date < period_from,
            Invoice.status != InvoiceStatus.cancelled,
        )
        .all()
    )
    opening_debit = sum((Decimal(i.total) for i in opening_q), Decimal(0))
    opening_pay_q = (
        db.query(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .filter(
            Invoice.customer_id == customer_id,
            Payment.paid_at < period_from,
        )
        .all()
    )
    opening_credit = sum((Decimal(p.amount) for p in opening_pay_q), Decimal(0))
    opening_balance = opening_debit - opening_credit

    # 기간 내 거래
    period_invs = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.issued_date >= period_from,
            Invoice.issued_date <= period_to,
            Invoice.status != InvoiceStatus.cancelled,
        )
        .all()
    )
    period_pays = (
        db.query(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .filter(
            Invoice.customer_id == customer_id,
            Payment.paid_at >= period_from,
            Payment.paid_at <= period_to,
        )
        .all()
    )

    events: list[tuple[date, str, Decimal, Decimal]] = []
    for i in period_invs:
        events.append((i.issued_date, f"{i.invoice_no} 매출", Decimal(i.total), Decimal(0)))
    for p in period_pays:
        events.append(
            (p.paid_at, f"입금 ({p.method})", Decimal(0), Decimal(p.amount))
        )
    events.sort(key=lambda e: e[0])

    rows: list[LedgerRow] = []
    running = Decimal(opening_balance)
    for ev_date, desc, debit, credit in events:
        running = running + debit - credit
        rows.append(
            LedgerRow(
                txn_date=ev_date,
                description=desc,
                debit=debit,
                credit=credit,
                balance=running,
            )
        )

    pdf = render_customer_ledger(
        company,
        customer,
        rows,
        period_from=period_from,
        period_to=period_to,
        opening_balance=opening_balance,
    )
    return _pdf_response(pdf, f"거래원장_{cust.name}_{period_from}_{period_to}.pdf")
