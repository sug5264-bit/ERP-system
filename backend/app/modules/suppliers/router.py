"""Suppliers + Purchase Orders + Supplier Portal.

Internal users (manager+) create POs and mark them as received. The supplier
portal is a constrained view: a supplier user (linked via Supplier.portal_user_id)
can only see their own POs and acknowledge / ship them.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    is_supplier_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.inventory.models import Item, MovementType
from app.modules.inventory.schemas import StockMovementCreate
from app.modules.inventory.service import create_movement
from app.modules.suppliers.models import (
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)
from app.modules.suppliers.schemas import (
    CreateSupplierWithPortalUser,
    POCreate,
    POOut,
    POReceive,
    SupplierIn,
    SupplierOut,
)

# Router-level auth allows supplier users — but the supplier-listing endpoints
# below require an internal user explicitly.
router = APIRouter(
    prefix="/api/suppliers",
    tags=["suppliers"],
    dependencies=[Depends(get_current_user)],
)


# ---- Supplier CRUD (internal-only) -----------------------------------------


@router.get(
    "",
    response_model=Page[SupplierOut],
    dependencies=[Depends(get_current_internal_user)],
)
def list_suppliers(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(db.query(Supplier).order_by(Supplier.code), params)


@router.post(
    "",
    response_model=SupplierOut,
    dependencies=[Depends(get_current_internal_user), Depends(require_role("admin"))],
)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db)):
    if db.query(Supplier).filter(Supplier.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    s = Supplier(**payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.post(
    "/with-portal-user",
    response_model=SupplierOut,
    dependencies=[Depends(get_current_internal_user), Depends(require_role("admin"))],
)
def create_supplier_with_portal_user(
    payload: CreateSupplierWithPortalUser,
    db: Session = Depends(get_db),
):
    """Create a Supplier and a paired portal-user account in one transaction.

    The portal user gets `Role.supplier` and is automatically linked via
    `Supplier.portal_user_id`.
    """
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    if db.query(Supplier).filter(Supplier.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Supplier code already exists")
    if db.query(User).filter(User.email == payload.contact_email).first():
        raise HTTPException(status_code=400, detail="Email already in use by a user")

    portal_user = User(
        email=payload.contact_email,
        full_name=payload.portal_full_name,
        hashed_password=hash_password(payload.portal_password),
        role=Role.supplier,
    )
    db.add(portal_user)
    db.flush()

    supplier = Supplier(
        code=payload.code,
        name=payload.name,
        contact_email=payload.contact_email,
        phone=payload.phone,
        business_no=payload.business_no,
        portal_user_id=portal_user.id,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


# ---- Purchase Orders -------------------------------------------------------


def _is_supplier_user(user: User, po: PurchaseOrder) -> bool:
    """A supplier-portal user only sees their own supplier's POs."""
    return po.supplier and po.supplier.portal_user_id == user.id


def _scoped_orders(db: Session, user: User):
    q = db.query(PurchaseOrder).options(
        selectinload(PurchaseOrder.supplier),
        selectinload(PurchaseOrder.items),
    )
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role in ("admin", "manager", "staff", "viewer"):
        return q
    # Supplier-portal users only see their own.
    if is_supplier_user(user):
        supplier = (
            db.query(Supplier).filter(Supplier.portal_user_id == user.id).first()
        )
        if supplier:
            return q.filter(PurchaseOrder.supplier_id == supplier.id)
        # Supplier role with no linked Supplier — see nothing.
        return q.filter(PurchaseOrder.id == -1)
    return q


@router.get("/orders", response_model=Page[POOut])
def list_orders(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return paginate(
        _scoped_orders(db, user).order_by(PurchaseOrder.order_date.desc()), params
    )


@router.post(
    "/orders", response_model=POOut, dependencies=[Depends(require_role("manager"))]
)
def create_order(
    payload: POCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.query(Supplier).filter(Supplier.id == payload.supplier_id).first():
        raise HTTPException(status_code=404, detail="Supplier not found")
    total = sum(
        (Decimal(line.quantity) * Decimal(line.unit_price) for line in payload.items),
        Decimal("0"),
    )
    po = PurchaseOrder(
        po_no=payload.po_no,
        supplier_id=payload.supplier_id,
        expected_date=payload.expected_date,
        notes=payload.notes,
        total=total,
        status=POStatus.draft,
        created_by_id=user.id,
    )
    for line in payload.items:
        po.items.append(PurchaseOrderItem(**line.model_dump()))
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


def _transition(
    db: Session, order_id: int, user: User, allowed_from: list[POStatus], to: POStatus
) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.supplier))
        .filter(PurchaseOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in allowed_from:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot move from {po.status.value} to {to.value}",
        )
    po.status = to
    db.commit()
    db.refresh(po)
    return po


@router.post("/orders/{order_id}/send", response_model=POOut)
def send_to_supplier(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Internal: send draft → supplier portal."""
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Manager required")
    return _transition(db, order_id, user, [POStatus.draft], POStatus.sent)


@router.post("/orders/{order_id}/acknowledge", response_model=POOut)
def acknowledge(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supplier-portal: confirm receipt of the PO."""
    po = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.supplier))
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in ("admin", "manager") and not _is_supplier_user(user, po):
        raise HTTPException(status_code=403, detail="Not your PO")
    return _transition(db, order_id, user, [POStatus.sent], POStatus.acknowledged)


@router.post("/orders/{order_id}/ship", response_model=POOut)
def mark_shipped(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supplier-portal: mark goods shipped."""
    po = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.supplier))
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in ("admin", "manager") and not _is_supplier_user(user, po):
        raise HTTPException(status_code=403, detail="Not your PO")
    return _transition(
        db, order_id, user, [POStatus.acknowledged, POStatus.sent], POStatus.shipped
    )


@router.post(
    "/orders/{order_id}/receive",
    response_model=POOut,
    dependencies=[Depends(require_role("staff"))],
)
def receive_goods(
    order_id: int,
    payload: POReceive,
    db: Session = Depends(get_db),
):
    """Internal: record goods received → create inbound stock movements."""
    po = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.items))
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in (POStatus.shipped, POStatus.acknowledged, POStatus.sent):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot receive a {po.status.value} order",
        )

    by_item = {l.item_id: l for l in po.items}
    for line in payload.lines:
        po_line = by_item.get(line.item_id)
        if not po_line:
            raise HTTPException(
                status_code=400, detail=f"item {line.item_id} not on this PO"
            )
        po_line.received_qty = Decimal(po_line.received_qty) + Decimal(line.quantity)
        # Inbound stock movement (auto-appends to ledger)
        create_movement(
            db,
            StockMovementCreate(
                item_id=line.item_id,
                type=MovementType.inbound,
                quantity=line.quantity,
                note=f"PO {po.po_no}",
            ),
        )

    fully = all(
        Decimal(l.received_qty) >= Decimal(l.quantity) for l in po.items
    )
    if fully:
        po.status = POStatus.received
    db.commit()
    db.refresh(po)
    return po


@router.post(
    "/orders/{order_id}/cancel",
    response_model=POOut,
    dependencies=[Depends(require_role("manager"))],
)
def cancel_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _transition(
        db,
        order_id,
        user,
        [POStatus.draft, POStatus.sent, POStatus.acknowledged],
        POStatus.cancelled,
    )


# ---- Admin-only edit / delete ---------------------------------------------


from app.modules.suppliers.schemas import SupplierUpdate  # noqa: E402


@router.patch(
    "/{supplier_id}",
    response_model=SupplierOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_supplier(
    supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)
):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sup, k, v)
    db.commit()
    db.refresh(sup)
    return sup


@router.delete(
    "/{supplier_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if db.query(PurchaseOrder).filter(PurchaseOrder.supplier_id == supplier_id).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete supplier with existing POs (cancel them first)",
        )
    db.delete(sup)
    db.commit()
    return {"ok": True}


# ---- Goods Receipt + 3-way matching ---------------------------------------


from datetime import date as _date  # noqa: E402
from decimal import Decimal as _D  # noqa: E402

from pydantic import BaseModel as _BM, ConfigDict as _Cfg, Field as _Field  # noqa: E402

from app.modules.inventory.schemas import StockMovementCreate as _StockMovementCreate  # noqa: E402
from app.modules.inventory.service import create_movement as _create_movement  # noqa: E402
from app.modules.inventory.models import MovementType as _MovementType  # noqa: E402
from app.modules.suppliers.models import (  # noqa: E402
    GRStatus,
    GoodsReceipt,
    GoodsReceiptItem,
    POStatus as _POStatus,
    PurchaseOrder as _PO,
    PurchaseOrderItem as _POItem,
    SupplierInvoice,
    SupplierInvoiceStatus,
)


class GRItemIn(_BM):
    po_item_id: int
    received_qty: _D
    lot_id: int | None = None


class GRIn(_BM):
    gr_no: str
    po_id: int
    received_date: _date | None = None
    notes: str | None = None
    items: list[GRItemIn] = _Field(min_length=1)


class GRItemOut(GRItemIn):
    id: int
    model_config = _Cfg(from_attributes=True)


class GROut(_BM):
    id: int
    gr_no: str
    po_id: int
    received_date: _date
    status: GRStatus
    notes: str | None
    items: list[GRItemOut]
    model_config = _Cfg(from_attributes=True)


class SupplierInvoiceIn(_BM):
    supplier_id: int
    po_id: int | None = None
    vendor_invoice_no: str
    invoice_date: _date
    subtotal: _D
    tax: _D = _D("0")
    total: _D


class SupplierInvoiceOut(SupplierInvoiceIn):
    id: int
    status: SupplierInvoiceStatus
    match_notes: str | None
    model_config = _Cfg(from_attributes=True)


@router.get("/goods-receipts", response_model=Page[GROut])
def list_grs(
    po_id: int | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    from sqlalchemy.orm import selectinload as _sel

    q = (
        db.query(GoodsReceipt)
        .options(_sel(GoodsReceipt.items))
        .order_by(GoodsReceipt.received_date.desc())
    )
    if po_id is not None:
        q = q.filter(GoodsReceipt.po_id == po_id)
    return paginate(q, params)


@router.post(
    "/goods-receipts",
    response_model=GROut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def create_gr(payload: GRIn, db: Session = Depends(get_db)):
    if db.query(GoodsReceipt).filter(GoodsReceipt.gr_no == payload.gr_no).first():
        raise HTTPException(status_code=400, detail="GR no already exists")
    po = (
        db.query(_PO)
        .filter(_PO.id == payload.po_id)
        .with_for_update()
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in (_POStatus.sent, _POStatus.acknowledged, _POStatus.shipped):
        raise HTTPException(
            status_code=400,
            detail=f"PO must be sent / acknowledged / shipped (got {po.status.value})",
        )

    # Pre-flight: check no line over-receives
    by_id = {pi.id: pi for pi in po.items}
    for li in payload.items:
        pi = by_id.get(li.po_item_id)
        if not pi:
            raise HTTPException(status_code=400, detail=f"PO item {li.po_item_id} not on this PO")
        if _D(pi.received_qty) + _D(li.received_qty) > _D(pi.quantity):
            raise HTTPException(
                status_code=400,
                detail=f"Over-receipt on PO item {pi.id}: "
                f"{pi.received_qty}+{li.received_qty} > {pi.quantity}",
            )

    gr = GoodsReceipt(
        gr_no=payload.gr_no,
        po_id=po.id,
        received_date=payload.received_date or _date.today(),
        notes=payload.notes,
        status=GRStatus.draft,
    )
    for li in payload.items:
        gr.items.append(GoodsReceiptItem(**li.model_dump()))
    db.add(gr)
    db.commit()
    db.refresh(gr)
    return gr


@router.post(
    "/goods-receipts/{gr_id}/post",
    response_model=GROut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def post_gr(gr_id: int, db: Session = Depends(get_db)):
    """Post a GR: bumps PO line received_qty and creates inbound movements."""
    from sqlalchemy.orm import selectinload as _sel

    gr = (
        db.query(GoodsReceipt)
        .options(_sel(GoodsReceipt.items))
        .filter(GoodsReceipt.id == gr_id)
        .with_for_update()
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="GR not found")
    if gr.status != GRStatus.draft:
        raise HTTPException(status_code=400, detail=f"Already {gr.status.value}")

    po = db.query(_PO).filter(_PO.id == gr.po_id).with_for_update().first()
    by_id = {pi.id: pi for pi in po.items}
    for li in gr.items:
        pi = by_id[li.po_item_id]
        # Update received_qty (with the lock held)
        pi.received_qty = _D(pi.received_qty) + _D(li.received_qty)
        try:
            _create_movement(
                db,
                _StockMovementCreate(
                    item_id=pi.item_id,
                    type=_MovementType.inbound,
                    quantity=li.received_qty,
                    unit_cost=pi.unit_price,
                    lot_id=li.lot_id,
                    note=f"GR {gr.gr_no} (PO {po.po_no})",
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # If every PO line is fully received, advance PO to received
    if all(_D(pi.received_qty) >= _D(pi.quantity) for pi in po.items):
        po.status = _POStatus.received

    gr.status = GRStatus.posted
    db.commit()
    db.refresh(gr)
    return gr


@router.get("/supplier-invoices", response_model=Page[SupplierInvoiceOut])
def list_sup_invoices(
    status: SupplierInvoiceStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(SupplierInvoice).order_by(SupplierInvoice.invoice_date.desc())
    if status:
        q = q.filter(SupplierInvoice.status == status)
    return paginate(q, params)


@router.post(
    "/supplier-invoices",
    response_model=SupplierInvoiceOut,
    dependencies=[Depends(require_module_role("finance", "staff"))],
)
def create_sup_invoice(payload: SupplierInvoiceIn, db: Session = Depends(get_db)):
    inv = SupplierInvoice(**payload.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/supplier-invoices/{inv_id}/match",
    response_model=SupplierInvoiceOut,
    dependencies=[Depends(require_module_role("finance", "manager"))],
)
def match_three_way(
    inv_id: int,
    tolerance: float = 0.01,
    db: Session = Depends(get_db),
):
    """3-way matching: PO ↔ sum(GR) ↔ SupplierInvoice.

    Passes if:
      • Every PO line's received_qty equals the ordered qty (within tolerance)
      • Sum(GR.qty * PO.unit_price) ≈ supplier invoice total (within tolerance)

    On pass: status → matched, ready for payment.
    On mismatch: status → rejected, with `match_notes` explaining why.
    """
    inv = (
        db.query(SupplierInvoice)
        .filter(SupplierInvoice.id == inv_id)
        .with_for_update()
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if inv.status == SupplierInvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Already paid")
    if not inv.po_id:
        raise HTTPException(status_code=400, detail="Invoice has no linked PO — manual review")

    po = (
        db.query(_PO)
        .filter(_PO.id == inv.po_id)
        .with_for_update()
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Linked PO not found")

    tol = _D(str(tolerance))
    issues: list[str] = []
    expected_total = _D("0")
    for pi in po.items:
        diff = _D(pi.quantity) - _D(pi.received_qty)
        if abs(diff) > tol:
            issues.append(
                f"PO line {pi.id}: ordered {pi.quantity}, received {pi.received_qty}"
            )
        expected_total += _D(pi.received_qty) * _D(pi.unit_price)

    inv_total_diff = abs(_D(inv.total) - expected_total - _D(inv.tax))
    if inv_total_diff > tol:
        issues.append(
            f"Total mismatch: invoice {inv.total} vs PO×GR+tax {expected_total + _D(inv.tax)}"
        )

    if issues:
        inv.status = SupplierInvoiceStatus.rejected
        inv.match_notes = "; ".join(issues)
    else:
        inv.status = SupplierInvoiceStatus.matched
        inv.match_notes = None
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/supplier-invoices/{inv_id}/mark-paid",
    response_model=SupplierInvoiceOut,
    dependencies=[Depends(require_role("admin"))],
)
def mark_sup_invoice_paid(inv_id: int, db: Session = Depends(get_db)):
    inv = (
        db.query(SupplierInvoice)
        .filter(SupplierInvoice.id == inv_id)
        .with_for_update()
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if inv.status != SupplierInvoiceStatus.matched:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pay invoice with status {inv.status.value} — must be matched first",
        )
    inv.status = SupplierInvoiceStatus.paid
    db.commit()
    db.refresh(inv)
    return inv


# ---- RFQ + Vendor scorecard -----------------------------------------------


from app.modules.suppliers.models import (  # noqa: E402
    RFQ,
    RFQItem,
    RFQResponse,
    RFQResponseLine,
    RFQResponseStatus,
    RFQStatus,
)


class RFQItemIn(_BM):
    item_id: int
    quantity: _D


class RFQIn(_BM):
    rfq_no: str
    title: str
    due_date: _date | None = None
    notes: str | None = None
    items: list[RFQItemIn] = _Field(min_length=1)


class RFQItemOut(_BM):
    id: int
    item_id: int
    quantity: _D
    model_config = _Cfg(from_attributes=True)


class RFQOut(_BM):
    id: int
    rfq_no: str
    title: str
    due_date: _date | None
    status: RFQStatus
    notes: str | None
    awarded_response_id: int | None
    items: list[RFQItemOut]
    model_config = _Cfg(from_attributes=True)


class RFQResponseLineIn(_BM):
    rfq_item_id: int
    unit_price: _D


class RFQResponseIn(_BM):
    rfq_id: int
    supplier_id: int
    lead_time_days: int | None = None
    notes: str | None = None
    lines: list[RFQResponseLineIn] = _Field(min_length=1)


class RFQResponseLineOut(RFQResponseLineIn):
    id: int
    model_config = _Cfg(from_attributes=True)


class RFQResponseOut(_BM):
    id: int
    rfq_id: int
    supplier_id: int
    total: _D
    lead_time_days: int | None
    status: RFQResponseStatus
    notes: str | None
    submitted_at: _date | None
    lines: list[RFQResponseLineOut]
    model_config = _Cfg(from_attributes=True)


@router.get("/rfqs", response_model=list[RFQOut])
def list_rfqs(status: RFQStatus | None = None, db: Session = Depends(get_db)):
    q = (
        db.query(RFQ)
        .options(selectinload(RFQ.items))
        .order_by(RFQ.created_at.desc())
    )
    if status:
        q = q.filter(RFQ.status == status)
    return q.all()


@router.post(
    "/rfqs",
    response_model=RFQOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def create_rfq(payload: RFQIn, db: Session = Depends(get_db)):
    if db.query(RFQ).filter(RFQ.rfq_no == payload.rfq_no).first():
        raise HTTPException(status_code=400, detail="RFQ no already exists")
    rfq = RFQ(
        rfq_no=payload.rfq_no, title=payload.title,
        due_date=payload.due_date, notes=payload.notes,
    )
    for it in payload.items:
        rfq.items.append(RFQItem(**it.model_dump()))
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    return rfq


@router.post(
    "/rfqs/{rfq_id}/send",
    response_model=RFQOut,
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def send_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).with_for_update().first()
    if not rfq:
        raise HTTPException(status_code=404, detail="Not found")
    if rfq.status != RFQStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot send from {rfq.status.value}")
    rfq.status = RFQStatus.sent
    db.commit()
    db.refresh(rfq)
    return rfq


@router.get("/rfqs/{rfq_id}/responses", response_model=list[RFQResponseOut])
def list_rfq_responses(rfq_id: int, db: Session = Depends(get_db)):
    return (
        db.query(RFQResponse)
        .options(selectinload(RFQResponse.lines))
        .filter(RFQResponse.rfq_id == rfq_id)
        .order_by(RFQResponse.total.asc())
        .all()
    )


@router.post("/rfqs/responses", response_model=RFQResponseOut)
def submit_rfq_response(payload: RFQResponseIn, db: Session = Depends(get_db)):
    """Supplier submits their bid. Computes total = sum(line.unit_price * rfq_item.quantity)."""
    rfq = (
        db.query(RFQ)
        .options(selectinload(RFQ.items))
        .filter(RFQ.id == payload.rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.status not in (RFQStatus.sent, RFQStatus.draft):
        raise HTTPException(status_code=400, detail=f"RFQ is {rfq.status.value}")
    existing = (
        db.query(RFQResponse)
        .filter(
            RFQResponse.rfq_id == payload.rfq_id,
            RFQResponse.supplier_id == payload.supplier_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Supplier already responded")

    items_by_id = {it.id: it for it in rfq.items}
    total = _D("0")
    for line in payload.lines:
        ri = items_by_id.get(line.rfq_item_id)
        if not ri:
            raise HTTPException(status_code=400,
                                  detail=f"RFQ item {line.rfq_item_id} not on this RFQ")
        total += _D(line.unit_price) * _D(ri.quantity)

    resp = RFQResponse(
        rfq_id=payload.rfq_id, supplier_id=payload.supplier_id,
        lead_time_days=payload.lead_time_days, notes=payload.notes,
        total=total, status=RFQResponseStatus.submitted,
        submitted_at=_date.today(),
    )
    for line in payload.lines:
        resp.lines.append(RFQResponseLine(**line.model_dump()))
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


@router.post(
    "/rfqs/{rfq_id}/award/{response_id}",
    dependencies=[Depends(require_module_role("inventory", "manager"))],
)
def award_rfq(rfq_id: int, response_id: int, db: Session = Depends(get_db)):
    """Award the RFQ to the chosen response → close RFQ + auto-generate a PO."""
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).with_for_update().first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.status not in (RFQStatus.sent, RFQStatus.draft):
        raise HTTPException(status_code=400, detail=f"Cannot award {rfq.status.value}")
    resp = (
        db.query(RFQResponse)
        .options(selectinload(RFQResponse.lines))
        .filter(RFQResponse.id == response_id, RFQResponse.rfq_id == rfq_id)
        .with_for_update()
        .first()
    )
    if not resp:
        raise HTTPException(status_code=404, detail="Response not found on this RFQ")

    # Mark other responses rejected
    db.query(RFQResponse).filter(
        RFQResponse.rfq_id == rfq_id, RFQResponse.id != response_id
    ).update({"status": RFQResponseStatus.rejected}, synchronize_session=False)

    resp.status = RFQResponseStatus.awarded
    rfq.awarded_response_id = resp.id
    rfq.status = RFQStatus.closed

    # Auto-PO
    from datetime import datetime as _dtnow

    rfq_items_by_id = {it.id: it for it in db.query(RFQItem).filter(RFQItem.rfq_id == rfq.id).all()}
    po = PurchaseOrder(
        po_no=f"PO-{rfq.rfq_no}",
        supplier_id=resp.supplier_id,
        status=POStatus.draft,
        notes=f"Auto-PO from RFQ {rfq.rfq_no}",
    )
    total = _D("0")
    for line in resp.lines:
        ri = rfq_items_by_id.get(line.rfq_item_id)
        if not ri:
            continue
        po.items.append(PurchaseOrderItem(
            item_id=ri.item_id, quantity=ri.quantity, unit_price=line.unit_price,
        ))
        total += _D(line.unit_price) * _D(ri.quantity)
    po.total = total
    db.add(po)
    db.commit()
    db.refresh(po)
    return {"rfq_id": rfq.id, "awarded_response_id": resp.id, "po_id": po.id, "po_no": po.po_no}


@router.get("/scorecard")
def vendor_scorecard(
    supplier_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Per-supplier KPI: on-time delivery rate, average lead time, match rate.

    Derived from PO + GR + SupplierInvoice tables. No persisted state.
    """
    from sqlalchemy import case, func as _f

    sup_q = db.query(Supplier)
    if supplier_id is not None:
        sup_q = sup_q.filter(Supplier.id == supplier_id)
    suppliers = sup_q.all()

    out = []
    for sup in suppliers:
        pos = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.supplier_id == sup.id,
                PurchaseOrder.status.in_([POStatus.received, POStatus.acknowledged, POStatus.shipped]),
            )
            .all()
        )
        if not pos:
            out.append({
                "supplier_id": sup.id, "supplier_code": sup.code, "supplier_name": sup.name,
                "po_count": 0, "on_time_rate": None, "avg_lead_time_days": None,
                "match_rate": None, "total_value": 0.0,
            })
            continue

        on_time = 0
        lead_times: list[int] = []
        total_value = _D("0")
        # On-time = last GR posted on/before expected_date
        for po in pos:
            total_value += _D(po.total)
            grs = (
                db.query(GoodsReceipt)
                .filter(GoodsReceipt.po_id == po.id, GoodsReceipt.status == GRStatus.posted)
                .order_by(GoodsReceipt.received_date.desc())
                .all()
            )
            if not grs:
                continue
            last = grs[0]
            if po.expected_date and last.received_date <= po.expected_date:
                on_time += 1
            lead_times.append((last.received_date - po.order_date).days)

        invs = db.query(SupplierInvoice).filter(SupplierInvoice.supplier_id == sup.id).all()
        matched = sum(1 for i in invs if i.status in (SupplierInvoiceStatus.matched, SupplierInvoiceStatus.paid))

        out.append({
            "supplier_id": sup.id,
            "supplier_code": sup.code,
            "supplier_name": sup.name,
            "po_count": len(pos),
            "on_time_rate": round(on_time / len(pos), 3) if pos else None,
            "avg_lead_time_days": (
                round(sum(lead_times) / len(lead_times), 1) if lead_times else None
            ),
            "match_rate": round(matched / len(invs), 3) if invs else None,
            "total_value": float(total_value),
        })
    return {"scorecard": out}
