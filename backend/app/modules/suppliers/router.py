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
