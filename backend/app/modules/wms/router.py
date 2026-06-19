"""WMS endpoints: generate pick list from sales order → pick → pack into
shipment → ship → deliver."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    require_module_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.inventory.models import MovementType
from app.modules.inventory.schemas import StockMovementCreate
from app.modules.inventory.service import create_movement
from app.modules.sales.models import OrderStatus, SalesOrder
from app.modules.wms.models import (
    PickList,
    PickListItem,
    PickStatus,
    Shipment,
    ShipmentStatus,
)

router = APIRouter(
    prefix="/api/wms",
    tags=["wms"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class PickListItemOut(BaseModel):
    id: int
    item_id: int
    requested_qty: Decimal
    picked_qty: Decimal
    lot_id: int | None
    location: str | None
    model_config = ConfigDict(from_attributes=True)


class PickListOut(BaseModel):
    id: int
    pick_no: str
    sales_order_id: int
    status: PickStatus
    picker_id: int | None
    started_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    items: list[PickListItemOut]
    model_config = ConfigDict(from_attributes=True)


class PickItemUpdate(BaseModel):
    item_id: int
    picked_qty: Decimal
    lot_id: int | None = None


class CompletePickIn(BaseModel):
    items: list[PickItemUpdate] = Field(min_length=1)


class ShipmentIn(BaseModel):
    shipment_no: str
    pick_list_id: int
    carrier: str | None = None
    tracking_no: str | None = None
    weight_kg: Decimal | None = None
    address_to: str | None = None


class ShipmentOut(BaseModel):
    id: int
    shipment_no: str
    pick_list_id: int
    sales_order_id: int
    status: ShipmentStatus
    carrier: str | None
    tracking_no: str | None
    weight_kg: Decimal | None
    packed_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    address_to: str | None
    notes: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- Pick lists ------------------------------------------------------------


@router.get("/pick-lists", response_model=Page[PickListOut])
def list_pick_lists(
    status: PickStatus | None = None,
    sales_order_id: int | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = (
        db.query(PickList)
        .options(selectinload(PickList.items))
        .order_by(PickList.created_at.desc())
    )
    if status:
        q = q.filter(PickList.status == status)
    if sales_order_id is not None:
        q = q.filter(PickList.sales_order_id == sales_order_id)
    return paginate(q, params)


@router.post(
    "/pick-lists/from-order/{order_id}",
    response_model=PickListOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def generate_pick_list(order_id: int, db: Session = Depends(get_db)):
    """Create a pick list from a confirmed sales order. One per order
    (unique constraint via pick_no = `PL-{order_no}`)."""
    so = (
        db.query(SalesOrder)
        .options(selectinload(SalesOrder.items))
        .filter(SalesOrder.id == order_id)
        .first()
    )
    if not so:
        raise HTTPException(status_code=404, detail="Order not found")
    if so.status != OrderStatus.confirmed:
        raise HTTPException(
            status_code=400,
            detail=f"Order must be confirmed (got {so.status.value})",
        )
    pick_no = f"PL-{so.order_no}"
    if db.query(PickList).filter(PickList.pick_no == pick_no).first():
        raise HTTPException(status_code=400, detail="Pick list already exists for this order")
    pl = PickList(pick_no=pick_no, sales_order_id=so.id)
    for line in so.items:
        pl.items.append(
            PickListItem(item_id=line.item_id, requested_qty=line.quantity)
        )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


@router.post(
    "/pick-lists/{pl_id}/start",
    response_model=PickListOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def start_picking(
    pl_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pl = db.query(PickList).filter(PickList.id == pl_id).with_for_update().first()
    if not pl:
        raise HTTPException(status_code=404, detail="Not found")
    if pl.status != PickStatus.pending:
        raise HTTPException(status_code=400, detail=f"Cannot start {pl.status.value}")
    pl.status = PickStatus.picking
    pl.picker_id = user.id
    pl.started_at = datetime.utcnow()
    db.commit()
    db.refresh(pl)
    return pl


@router.post(
    "/pick-lists/{pl_id}/complete",
    response_model=PickListOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def complete_picking(
    pl_id: int,
    payload: CompletePickIn,
    db: Session = Depends(get_db),
):
    """Record actually-picked quantities (per item, optional lot). Allows
    short picks — Shipment generation will reflect what's actually packed.

    Note: Sales order confirm has already deducted inventory; complete just
    records what the picker grabbed off the shelf for traceability.
    """
    pl = (
        db.query(PickList)
        .options(selectinload(PickList.items))
        .filter(PickList.id == pl_id)
        .with_for_update()
        .first()
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Not found")
    if pl.status != PickStatus.picking:
        raise HTTPException(status_code=400, detail=f"Cannot complete {pl.status.value}")

    by_item = {it.item_id: it for it in pl.items}
    for upd in payload.items:
        line = by_item.get(upd.item_id)
        if not line:
            raise HTTPException(
                status_code=400, detail=f"Item {upd.item_id} not on this pick list"
            )
        if upd.picked_qty < 0 or upd.picked_qty > Decimal(line.requested_qty):
            raise HTTPException(
                status_code=400,
                detail=f"picked_qty {upd.picked_qty} out of range for item {upd.item_id}",
            )
        line.picked_qty = upd.picked_qty
        if upd.lot_id is not None:
            line.lot_id = upd.lot_id

    # Reject an all-zero completion — a totally empty pick should be cancelled,
    # not marked picked (would otherwise create empty shipments).
    if not any(Decimal(l.picked_qty) > 0 for l in pl.items):
        raise HTTPException(
            status_code=400,
            detail="No items were picked — cancel the pick list instead",
        )

    pl.status = PickStatus.picked
    pl.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(pl)
    return pl


# ---- Shipments -------------------------------------------------------------


@router.get("/shipments", response_model=Page[ShipmentOut])
def list_shipments(
    status: ShipmentStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Shipment).order_by(Shipment.created_at.desc())
    if status:
        q = q.filter(Shipment.status == status)
    return paginate(q, params)


@router.post(
    "/shipments",
    response_model=ShipmentOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def create_shipment(payload: ShipmentIn, db: Session = Depends(get_db)):
    """Pack a picked list into a shipment. The pick list must be in `picked`
    status. Shipment starts as `pending` (= packed but not yet handed to carrier).
    """
    pl = (
        db.query(PickList)
        .filter(PickList.id == payload.pick_list_id)
        .with_for_update()
        .first()
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Pick list not found")
    if pl.status != PickStatus.picked:
        raise HTTPException(
            status_code=400, detail=f"Pick list must be picked (got {pl.status.value})"
        )
    if db.query(Shipment).filter(Shipment.shipment_no == payload.shipment_no).first():
        raise HTTPException(status_code=400, detail="Shipment no exists")

    s = Shipment(
        shipment_no=payload.shipment_no,
        pick_list_id=pl.id,
        sales_order_id=pl.sales_order_id,
        carrier=payload.carrier,
        tracking_no=payload.tracking_no,
        weight_kg=payload.weight_kg,
        address_to=payload.address_to,
        status=ShipmentStatus.packed,
        packed_at=datetime.utcnow(),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.post(
    "/shipments/{ship_id}/ship",
    response_model=ShipmentOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def mark_shipped(ship_id: int, db: Session = Depends(get_db)):
    s = db.query(Shipment).filter(Shipment.id == ship_id).with_for_update().first()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status != ShipmentStatus.packed:
        raise HTTPException(status_code=400, detail=f"Cannot ship {s.status.value}")
    s.status = ShipmentStatus.shipped
    s.shipped_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    return s


@router.post(
    "/shipments/{ship_id}/deliver",
    response_model=ShipmentOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def mark_delivered(ship_id: int, db: Session = Depends(get_db)):
    s = db.query(Shipment).filter(Shipment.id == ship_id).with_for_update().first()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status != ShipmentStatus.shipped:
        raise HTTPException(status_code=400, detail=f"Cannot deliver {s.status.value}")
    s.status = ShipmentStatus.delivered
    s.delivered_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    return s


# ---- Document PDFs (거래명세표 / 인수증) ------------------------------------


def _shipment_to_line_items(
    db: Session, shipment: Shipment, *, vat_rate: Decimal = Decimal("0.10")
):
    """Pick list 라인 → docs_pdf LineItem 변환.

    - 단가는 SalesOrderItem.unit_price 우선 (실제 판매가), 없으면 Item.unit_price
    - 수량은 picked_qty 우선, 0이면 requested_qty
    - 바코드는 Item.barcode (양식에 표기)
    - 부가세는 라인별 10% (면세품은 호출자가 vat_rate=0으로 호출)
    """
    from app.core.docs_pdf import LineItem
    from app.modules.inventory.models import Item
    from app.modules.sales.models import SalesOrderItem

    pl = (
        db.query(PickList)
        .options(selectinload(PickList.items))
        .filter(PickList.id == shipment.pick_list_id)
        .first()
    )
    if not pl:
        return []
    item_ids = [li.item_id for li in pl.items]
    items_by_id = {
        i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()
    }
    # 실제 판매가는 SO 라인에 있음
    so_lines = (
        db.query(SalesOrderItem)
        .filter(SalesOrderItem.order_id == shipment.sales_order_id)
        .all()
    )
    so_price_by_item: dict[int, Decimal] = {}
    for sol in so_lines:
        # 동일 item이 여러 라인이면 첫 라인 단가 사용
        so_price_by_item.setdefault(sol.item_id, Decimal(sol.unit_price))

    lines: list[LineItem] = []
    for idx, li in enumerate(pl.items, start=1):
        qty = Decimal(li.picked_qty) if Decimal(li.picked_qty) > 0 else Decimal(li.requested_qty)
        prod = items_by_id.get(li.item_id)
        if not prod:
            continue
        unit_price = so_price_by_item.get(li.item_id, Decimal(prod.unit_price or 0))
        supply = (qty * unit_price).quantize(Decimal("1"))
        tax = (supply * vat_rate).quantize(Decimal("1"))
        lines.append(
            LineItem(
                no=idx,
                name=prod.name,
                spec=prod.sku,
                qty=qty,
                unit=prod.unit or "EA",
                unit_price=unit_price,
                supply_amount=supply,
                tax_amount=tax,
                barcode=prod.barcode or "",
                remark=None,
            )
        )
    return lines


def _customer_balances(
    db: Session, customer_id: int, as_of: date
) -> tuple[Decimal, Decimal, Decimal]:
    """거래처 외상매출금 잔액 계산.

    Returns:
        (전잔, 이번건 금액분, 후잔)  — 이번건은 호출자가 채움.
    여기서는 전잔(as_of 이전까지의 미수금) 반환만 담당.
    """
    from app.modules.billing.models import Invoice, InvoiceStatus, Payment

    inv_total = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.issued_date < as_of,
            Invoice.status != InvoiceStatus.cancelled,
        )
        .all()
    )
    debit = sum((Decimal(i.total) for i in inv_total), Decimal(0))
    pay_total = (
        db.query(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .filter(
            Invoice.customer_id == customer_id,
            Payment.paid_at < as_of,
        )
        .all()
    )
    credit = sum((Decimal(p.amount) for p in pay_total), Decimal(0))
    opening = debit - credit
    return opening, Decimal(0), opening  # closing은 호출자가 +이번건으로 계산


def _resolve_company_and_customer(db: Session, shipment: Shipment):
    """공급자(자사)와 공급받는자(거래처) PartyInfo 구성."""
    from app.core.docs_pdf import PartyInfo
    from app.modules.company.router import get_company_profile
    from app.modules.sales.models import Customer

    so = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == shipment.sales_order_id)
        .first()
    )
    cust = (
        db.query(Customer).filter(Customer.id == so.customer_id).first() if so else None
    )
    tenant_id = so.tenant_id if so else None
    cp = get_company_profile(db, tenant_id)
    if not cp:
        raise HTTPException(
            status_code=400,
            detail="회사정보(CompanyProfile)가 등록되어 있지 않습니다. PUT /api/company-profile 로 먼저 등록하세요.",
        )
    company = PartyInfo(
        business_no=cp.business_no,
        company_name=cp.company_name,
        representative=cp.representative,
        address=cp.address,
        business_type=cp.business_type,
        business_item=cp.business_item,
        phone=cp.phone,
        fax=cp.fax,
        logo_bytes=cp.logo_bytes,
        stamp_bytes=cp.stamp_bytes,
        logo_path=cp.logo_path,    # deprecated fallback
        stamp_path=cp.stamp_path,
    )
    if not cust:
        raise HTTPException(status_code=404, detail="거래처 정보를 찾을 수 없습니다.")
    customer = PartyInfo(
        business_no=cust.business_no,
        company_name=cust.company or cust.name,
        representative=cust.representative,
        address=cust.address,
        business_type=cust.business_type,
        business_item=cust.business_item,
        phone=cust.phone,
        fax=cust.fax,
    )
    return company, customer, cp


def _pdf_response(pdf_bytes: bytes, filename: str):
    import io as _io

    from fastapi.responses import StreamingResponse

    from app.core.exports import _content_disposition

    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename, inline=True)},
    )


def _txn_bank_info_line(cp) -> str | None:
    if not (cp.bank_name and cp.bank_account):
        return None
    holder = f" ({cp.bank_holder})" if cp.bank_holder else ""
    return f"{cp.bank_name} {cp.bank_account}{holder}"


def _serial_for(shipment: Shipment, doc_date: date) -> str:
    """일련번호 = 'YYYY/MM/DD -ID'  (사용자 양식과 동일)."""
    return f"{doc_date.strftime('%Y/%m/%d')} -{shipment.id}"


@router.get("/shipments/{ship_id}/transaction-statement.pdf")
def shipment_transaction_statement_pdf(
    ship_id: int, db: Session = Depends(get_db)
):
    """거래명세표 PDF — 실무 표준 양식 (A4 1장 보관용+인수용 2부).

    customer_type='individual' (일반 소비자) 인 경우 사업자 정보가 비어있어
    빈 양식이 나오므로, 자동으로 간이 영수증(render_simple_receipt)으로 전환.
    """
    from app.core.docs_pdf import render_simple_receipt, render_transaction_statement_v2
    from app.modules.sales.models import Customer, CustomerType

    s = db.query(Shipment).filter(Shipment.id == ship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    company, customer, cp = _resolve_company_and_customer(db, s)
    lines = _shipment_to_line_items(db, s)
    doc_date = (s.shipped_at or s.packed_at or datetime.utcnow()).date()

    # 고객 유형 확인 — individual 이면 간이 영수증
    so = db.query(SalesOrder).filter(SalesOrder.id == s.sales_order_id).first()
    raw_cust = (
        db.query(Customer).filter(Customer.id == so.customer_id).first() if so else None
    )
    if raw_cust and raw_cust.customer_type == CustomerType.individual:
        pdf = render_simple_receipt(
            company,
            customer_name=raw_cust.name,
            items=lines,
            doc_no=s.shipment_no,
            doc_date=doc_date,
            delivery_address=s.address_to,
            shop_name=raw_cust.external_source,
        )
        return _pdf_response(pdf, f"영수증_{s.shipment_no}.pdf")

    # 사업자 거래처 — 표준 거래명세서 (2부)
    opening, _, _ = _customer_balances(
        db, _customer_id_of(db, s), doc_date
    )
    this_total = sum((Decimal(l.supply_amount) + Decimal(l.tax_amount) for l in lines), Decimal(0))
    closing = opening + this_total

    pdf = render_transaction_statement_v2(
        company,
        customer,
        lines,
        serial_no=_serial_for(s, doc_date),
        doc_date=doc_date,
        bank_info=_txn_bank_info_line(cp),
        opening_balance=opening,
        closing_balance=closing,
        copies=2,
    )
    return _pdf_response(pdf, f"거래명세표_{s.shipment_no}.pdf")


@router.get("/shipments/{ship_id}/acceptance-receipt.pdf")
def shipment_acceptance_receipt_pdf(
    ship_id: int, db: Session = Depends(get_db)
):
    """인수증 PDF — 가격 정보 일체 숨김 (단가/공급가액/부가세/합계/잔액 X).

    수령인에게 마진/원가가 노출되지 않도록 함. 수량과 품명만 보고 사인/도장.
    """
    from app.core.docs_pdf import render_acceptance_receipt_v2

    s = db.query(Shipment).filter(Shipment.id == ship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    company, customer, _ = _resolve_company_and_customer(db, s)
    lines = _shipment_to_line_items(db, s)

    doc_date = (s.delivered_at or s.shipped_at or s.packed_at or datetime.utcnow()).date()
    pdf = render_acceptance_receipt_v2(
        company,
        customer,
        lines,
        serial_no=_serial_for(s, doc_date),
        doc_date=doc_date,
    )
    return _pdf_response(pdf, f"인수증_{s.shipment_no}.pdf")


def _customer_id_of(db: Session, shipment: Shipment) -> int:
    so = db.query(SalesOrder).filter(SalesOrder.id == shipment.sales_order_id).first()
    return so.customer_id if so else 0


@router.post(
    "/shipments/{ship_id}/return",
    response_model=ShipmentOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def mark_returned(ship_id: int, db: Session = Depends(get_db)):
    """Customer returned the shipment. Restocks the original picked items."""
    s = db.query(Shipment).filter(Shipment.id == ship_id).with_for_update().first()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status not in (ShipmentStatus.shipped, ShipmentStatus.delivered):
        raise HTTPException(status_code=400, detail=f"Cannot return {s.status.value}")

    # Restock from the linked pick list
    pl = (
        db.query(PickList)
        .options(selectinload(PickList.items))
        .filter(PickList.id == s.pick_list_id)
        .first()
    )
    for line in pl.items:
        if Decimal(line.picked_qty) <= 0:
            continue
        try:
            create_movement(
                db,
                StockMovementCreate(
                    item_id=line.item_id,
                    lot_id=line.lot_id,  # preserve lot traceability on return
                    type=MovementType.inbound,
                    quantity=line.picked_qty,
                    note=f"Return from shipment {s.shipment_no}",
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    s.status = ShipmentStatus.returned
    db.commit()
    db.refresh(s)
    return s


# ─── 출고 → 청구서 자동 draft ────────────────────────────────────────


@router.post(
    "/shipments/{ship_id}/generate-invoice",
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def generate_invoice_from_shipment(
    ship_id: int,
    tax_rate: Decimal = Decimal("0.10"),
    db: Session = Depends(get_db),
):
    """출고 1건 → 청구서(Invoice) draft 자동 생성.

    - 동일 shipment의 invoice가 이미 있으면 기존 ID를 반환 (멱등)
    - line_total은 picked_qty * SO 라인 단가
    - 부가세는 tax_rate (기본 10%, 면세는 0)
    - invoice_no 자동 생성: 'INV-<shipment_no>'
    - draft 상태로 저장 — 발행은 별도 /api/billing/invoices/{id}/issue 호출
    """
    from app.modules.billing.models import Invoice, InvoiceItem, InvoiceStatus
    from app.modules.inventory.models import Item
    from app.modules.sales.models import SalesOrderItem

    s = db.query(Shipment).filter(Shipment.id == ship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    so = db.query(SalesOrder).filter(SalesOrder.id == s.sales_order_id).first()
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")

    invoice_no = f"INV-{s.shipment_no}"
    existing = db.query(Invoice).filter(Invoice.invoice_no == invoice_no).first()
    if existing:
        return {
            "invoice_id": existing.id,
            "invoice_no": existing.invoice_no,
            "status": existing.status.value,
            "already_exists": True,
        }

    pl = (
        db.query(PickList)
        .options(selectinload(PickList.items))
        .filter(PickList.id == s.pick_list_id)
        .first()
    )
    if not pl or not pl.items:
        raise HTTPException(
            status_code=400, detail="출고할 품목이 없어 청구서 생성 불가"
        )

    # 단가 매핑 (SO 라인 단가 우선)
    so_lines = (
        db.query(SalesOrderItem)
        .filter(SalesOrderItem.order_id == so.id)
        .all()
    )
    so_price_by_item: dict[int, Decimal] = {}
    for sol in so_lines:
        so_price_by_item.setdefault(sol.item_id, Decimal(sol.unit_price))

    item_ids = [li.item_id for li in pl.items]
    items_by_id = {
        i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()
    }

    inv = Invoice(
        invoice_no=invoice_no,
        customer_id=so.customer_id,
        sales_order_id=so.id,
        status=InvoiceStatus.draft,
        notes=f"출고 {s.shipment_no} 자동 생성",
    )
    subtotal = Decimal(0)
    for li in pl.items:
        qty = Decimal(li.picked_qty) if Decimal(li.picked_qty) > 0 else Decimal(li.requested_qty)
        if qty <= 0:
            continue
        prod = items_by_id.get(li.item_id)
        if not prod:
            continue
        unit_price = so_price_by_item.get(li.item_id, Decimal(prod.unit_price or 0))
        line_total = (qty * unit_price).quantize(Decimal("0.01"))
        subtotal += line_total
        inv.items.append(
            InvoiceItem(
                description=prod.name,
                item_id=prod.id,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
    # 빈 invoice(라인 0건 또는 0원) 거부 — 운영자가 잘못 누른 결과 방지
    if not inv.items:
        raise HTTPException(
            status_code=400,
            detail="출고된 수량이 0이거나 단가 미설정 — 청구서 생성 불가",
        )
    inv.subtotal = subtotal
    inv.tax = (subtotal * Decimal(tax_rate)).quantize(Decimal("0.01"))
    inv.total = inv.subtotal + inv.tax
    if inv.total <= 0:
        raise HTTPException(
            status_code=400, detail="청구 금액이 0원 — 단가를 확인하세요."
        )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return {
        "invoice_id": inv.id,
        "invoice_no": inv.invoice_no,
        "status": inv.status.value,
        "subtotal": float(inv.subtotal),
        "tax": float(inv.tax),
        "total": float(inv.total),
        "already_exists": False,
    }


# ─── 송장번호 일괄 import (Excel/CSV) ────────────────────────────────


@router.get("/shipments/import-template")
def shipments_import_template(format: str = Query("xlsx")):
    """송장 일괄등록 양식 — 출고 후 운송장번호 한꺼번에 등록할 때 사용."""
    from app.core.exports import export_table

    headers = ["송장번호(SHP)", "택배사", "운송장번호", "무게(kg)"]
    sample = [
        ["SHP-WEB-20260619-001", "CJ대한통운", "612345678901", 2.5],
        ["SHP-WEB-20260619-002", "한진택배", "789012345678", 1.2],
    ]
    return export_table(sample, headers, "shipments_import_template", format)


@router.post(
    "/shipments/import-tracking",
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
async def import_shipment_tracking(
    file: UploadFile = File(...),
    auto_ship: bool = Query(
        True, description="True면 일괄 등록과 동시에 'shipped' 전이"
    ),
    db: Session = Depends(get_db),
):
    """택배사/운송장번호를 Excel/CSV로 일괄 등록.

    송장번호(SHP) 컬럼으로 Shipment 매칭. 매칭 안되면 errors 누적.
    auto_ship=True면 등록 후 즉시 ShipmentStatus.shipped로 전이 + shipped_at 기록.
    """
    from datetime import datetime as _dt

    from app.core.imports import parse_upload

    alias = {
        "송장번호": "shipment_no", "송장": "shipment_no", "shipment_no": "shipment_no",
        "송장번호(shp)": "shipment_no", "shp": "shipment_no",
        "택배사": "carrier", "carrier": "carrier", "택배": "carrier",
        "운송장번호": "tracking_no", "운송장": "tracking_no", "tracking_no": "tracking_no",
        "tracking": "tracking_no",
        "무게": "weight_kg", "무게(kg)": "weight_kg", "weight": "weight_kg",
        "weight_kg": "weight_kg",
    }
    rows = await parse_upload(file, alias)

    from decimal import Decimal as _D, InvalidOperation
    updated = 0
    shipped = 0
    skipped = 0
    errors: list[dict] = []

    for idx, r in enumerate(rows, start=2):
        shp_no = str(r.get("shipment_no") or "").strip()
        if not shp_no:
            errors.append({"row": idx, "reason": "송장번호 비어있음"})
            continue
        s = db.query(Shipment).filter(Shipment.shipment_no == shp_no).first()
        if not s:
            errors.append({"row": idx, "reason": f"매칭되는 출고 없음: {shp_no}"})
            continue
        carrier = str(r.get("carrier") or "").strip() or None
        tracking = str(r.get("tracking_no") or "").strip() or None
        weight = r.get("weight_kg")
        try:
            weight_dec = _D(str(weight)) if weight not in (None, "") else None
        except InvalidOperation:
            weight_dec = None

        if carrier:
            s.carrier = carrier
        if tracking:
            s.tracking_no = tracking
        if weight_dec is not None:
            s.weight_kg = weight_dec

        if auto_ship and s.status == ShipmentStatus.packed:
            s.status = ShipmentStatus.shipped
            s.shipped_at = _dt.utcnow()
            shipped += 1
        elif auto_ship and s.status != ShipmentStatus.packed:
            skipped += 1  # 이미 출하/배송완료 등
        updated += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {exc}")

    return {
        "updated": updated,
        "shipped": shipped,
        "skipped_not_packed": skipped,
        "errors": errors,
        "total_rows": len(rows),
    }
