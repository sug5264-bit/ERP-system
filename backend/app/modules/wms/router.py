"""WMS endpoints: generate pick list from sales order → pick → pack into
shipment → ship → deliver."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
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

    수량은 picked_qty 우선, 0이면 requested_qty.
    부가세는 라인별 10% (면세품은 호출자가 vat_rate=0으로 호출).
    """
    from app.core.docs_pdf import LineItem
    from app.modules.inventory.models import Item

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
    lines: list[LineItem] = []
    for idx, li in enumerate(pl.items, start=1):
        qty = Decimal(li.picked_qty) if Decimal(li.picked_qty) > 0 else Decimal(li.requested_qty)
        prod = items_by_id.get(li.item_id)
        if not prod:
            continue
        unit_price = Decimal(prod.unit_price or 0)
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
            )
        )
    return lines


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


@router.get("/shipments/{ship_id}/transaction-statement.pdf")
def shipment_transaction_statement_pdf(
    ship_id: int, db: Session = Depends(get_db)
):
    """거래명세표 PDF — 출고건 기준."""
    from app.core.docs_pdf import render_transaction_statement

    s = db.query(Shipment).filter(Shipment.id == ship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    company, customer, cp = _resolve_company_and_customer(db, s)
    lines = _shipment_to_line_items(db, s)
    bank_info = None
    if cp.bank_name and cp.bank_account:
        bank_info = f"{cp.bank_name} {cp.bank_account}" + (
            f" (예금주: {cp.bank_holder})" if cp.bank_holder else ""
        )
    pdf = render_transaction_statement(
        company,
        customer,
        lines,
        doc_no=s.shipment_no,
        doc_date=(s.shipped_at or s.packed_at or datetime.utcnow()).date(),
        bank_info=bank_info,
        remarks=s.notes,
    )
    return _pdf_response(pdf, f"거래명세표_{s.shipment_no}.pdf")


@router.get("/shipments/{ship_id}/acceptance-receipt.pdf")
def shipment_acceptance_receipt_pdf(
    ship_id: int, db: Session = Depends(get_db)
):
    """인수증 PDF — 출고건 기준."""
    from app.core.docs_pdf import render_acceptance_receipt

    s = db.query(Shipment).filter(Shipment.id == ship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    company, customer, _ = _resolve_company_and_customer(db, s)
    lines = _shipment_to_line_items(db, s)
    pdf = render_acceptance_receipt(
        company,
        customer,
        lines,
        doc_no=s.shipment_no,
        doc_date=(s.delivered_at or s.shipped_at or s.packed_at or datetime.utcnow()).date(),
        delivery_address=s.address_to,
    )
    return _pdf_response(pdf, f"인수증_{s.shipment_no}.pdf")


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
