from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import (
    get_current_user,
    get_current_internal_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.modules.inventory import service
from app.modules.inventory.models import Item, StockLot, StockMovement
from app.modules.inventory.schemas import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    StockLotIn,
    StockLotOut,
    StockLotUpdate,
    StockMovementCreate,
    StockMovementOut,
)

router = APIRouter(
    prefix="/api/inventory",
    tags=["inventory"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("/items", response_model=Page[ItemOut])
def list_items(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(db.query(Item).order_by(Item.sku), params)


@router.get("/items/export")
def export_items(format: str = Query("csv"), inline: bool = Query(False), db: Session = Depends(get_db)):
    items = service.list_items(db)
    headers = ["SKU", "품목명", "단위", "단가", "재고", "재고가치"]
    rows = [
        [
            i.sku,
            i.name,
            i.unit,
            float(i.unit_price),
            float(i.stock_qty),
            float(i.unit_price) * float(i.stock_qty),
        ]
        for i in items
    ]
    return export_table(rows, headers, "items", format, inline=inline)


@router.post(
    "/items",
    response_model=ItemOut,
    dependencies=[Depends(require_module_role("inventory", "admin"))],
)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    return service.create_item(db, payload)


@router.get("/movements", response_model=Page[StockMovementOut])
def list_movements(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(
        db.query(StockMovement).order_by(StockMovement.moved_at.desc()),
        params,
    )


@router.post(
    "/movements",
    response_model=StockMovementOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def create_movement(payload: StockMovementCreate, db: Session = Depends(get_db)):
    try:
        return service.create_movement(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/items/{item_id}/lots", response_model=list[StockLotOut])
def list_lots(item_id: int, db: Session = Depends(get_db)):
    return service.list_lots(db, item_id)


@router.post(
    "/items/{item_id}/consume-fefo",
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def consume_fefo(
    item_id: int,
    quantity: float,
    note: str = "FEFO outbound",
    db: Session = Depends(get_db),
):
    """Consume from lots in First-Expire-First-Out order.

    Lots with the earliest expiry_date are used first; lots without an expiry
    date are used last. Critical for F&B compliance.
    """
    from decimal import Decimal as _D

    try:
        movements = service.consume_fefo(db, item_id, _D(str(quantity)), note=note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "consumed": sum((float(m.quantity) for m in movements), 0.0),
        "movements": [
            {
                "id": m.id,
                "lot_id": m.lot_id,
                "quantity": float(m.quantity),
            }
            for m in movements
        ],
    }


@router.get("/lots/expiring")
def list_expiring_lots(
    within_days: int = 30,
    item_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Lots expiring within `within_days` (default 30). Sorted soonest-first."""
    rows = service.expiring_lots(db, within_days=within_days, item_id=item_id)
    return [
        {
            "id": r.id,
            "item_id": r.item_id,
            "lot_number": r.lot_number,
            "quantity": float(r.quantity),
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
            "supplier": r.supplier,
        }
        for r in rows
    ]


@router.post(
    "/items/{item_id}/lots",
    response_model=StockLotOut,
    dependencies=[Depends(require_module_role("inventory", "staff"))],
)
def create_lot(item_id: int, payload: StockLotIn, db: Session = Depends(get_db)):
    try:
        return service.create_lot(db, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---- Admin-only edit / delete ---------------------------------------------


@router.patch(
    "/items/{item_id}",
    response_model=ItemOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_item(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.modules.audit.diff import record_update, snapshot

    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    fields = ["sku", "name", "unit", "unit_price", "stock_qty"]
    before = snapshot(item, fields)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    after = snapshot(item, fields)
    record_update(
        db,
        resource_type="inv_items",
        resource_id=item.id,
        before=before,
        after=after,
        user_id=user.id,
        user_email=user.email,
        path=f"/api/inventory/items/{item.id}",
    )
    return item


@router.delete(
    "/items/{item_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    """Refuse if the item still has stock or any movement / lot history."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    from decimal import Decimal as _Dec

    if _Dec(item.stock_qty) != 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete item with non-zero stock ({item.stock_qty})",
        )
    if db.query(StockMovement).filter(StockMovement.item_id == item_id).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete item with movement history",
        )
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.patch(
    "/lots/{lot_id}",
    response_model=StockLotOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_lot(lot_id: int, payload: StockLotUpdate, db: Session = Depends(get_db)):
    lot = db.query(StockLot).filter(StockLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(lot, k, v)
    db.commit()
    db.refresh(lot)
    return lot


@router.delete(
    "/lots/{lot_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_lot(lot_id: int, db: Session = Depends(get_db)):
    lot = db.query(StockLot).filter(StockLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    from decimal import Decimal as _Dec

    if _Dec(lot.quantity) != 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete lot with non-zero quantity ({lot.quantity})",
        )
    db.delete(lot)
    db.commit()
    return {"ok": True}


# ---- Warehouses + per-warehouse stock --------------------------------------


from app.modules.inventory.models import Warehouse, WarehouseStock  # noqa: E402
from app.modules.inventory.schemas import (  # noqa: E402
    WarehouseIn,
    WarehouseOut,
    WarehouseStockOut,
)


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db)):
    return db.query(Warehouse).order_by(Warehouse.code).all()


@router.post(
    "/warehouses",
    response_model=WarehouseOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_warehouse(payload: WarehouseIn, db: Session = Depends(get_db)):
    if db.query(Warehouse).filter(Warehouse.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    w = Warehouse(**payload.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.get(
    "/items/{item_id}/stock-by-warehouse",
    response_model=list[WarehouseStockOut],
)
def stock_by_warehouse(item_id: int, db: Session = Depends(get_db)):
    return (
        db.query(WarehouseStock)
        .filter(WarehouseStock.item_id == item_id)
        .order_by(WarehouseStock.warehouse_id)
        .all()
    )


# ---- ABC analysis + reorder + auto-PO -------------------------------------


from datetime import datetime as _dt2, timedelta as _td2  # noqa: E402
from decimal import Decimal  # noqa: E402

from pydantic import BaseModel as _BM2, ConfigDict as _Cfg2  # noqa: E402

from app.core.auth import require_role as _require_role  # noqa: E402
from app.modules.inventory.models import (  # noqa: E402
    ABCClass,
    ItemPolicy,
    MovementType,
)


class ItemPolicyIn(_BM2):
    item_id: int
    reorder_point: Decimal = Decimal("0")
    safety_stock: Decimal = Decimal("0")
    reorder_qty: Decimal = Decimal("0")
    preferred_supplier_id: int | None = None


class ItemPolicyOut(ItemPolicyIn):
    id: int
    abc_class: ABCClass | None
    last_classified_at: _dt2 | None
    model_config = _Cfg2(from_attributes=True)


@router.get("/policies", response_model=list[ItemPolicyOut])
def list_policies(db: Session = Depends(get_db)):
    return db.query(ItemPolicy).order_by(ItemPolicy.item_id).all()


@router.put(
    "/policies",
    response_model=ItemPolicyOut,
    dependencies=[Depends(_require_role("manager"))],
)
def upsert_policy(payload: ItemPolicyIn, db: Session = Depends(get_db)):
    """Create or replace the stocking policy for an item."""
    pol = (
        db.query(ItemPolicy)
        .filter(ItemPolicy.item_id == payload.item_id)
        .with_for_update()
        .first()
    )
    if pol:
        for k, v in payload.model_dump().items():
            setattr(pol, k, v)
    else:
        pol = ItemPolicy(**payload.model_dump())
        db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol


@router.post(
    "/abc-classify",
    dependencies=[Depends(_require_role("manager"))],
)
def abc_classify(
    days: int = 365,
    db: Session = Depends(get_db),
):
    """Classify every item into A/B/C based on outbound value over the last
    `days` days. Pareto split: top 80% cumulative value = A, next 15% = B,
    remainder = C. Items with zero outbound default to C."""
    cutoff = _dt2.utcnow() - _td2(days=days)
    rows = (
        db.query(StockMovement)
        .filter(
            StockMovement.type == MovementType.outbound,
            StockMovement.moved_at >= cutoff,
        )
        .all()
    )
    # Aggregate value per item
    value_by_item: dict[int, Decimal] = {}
    for m in rows:
        unit = Decimal(m.unit_cost or 0)
        val = Decimal(m.quantity) * unit
        value_by_item[m.item_id] = value_by_item.get(m.item_id, Decimal("0")) + val

    if not value_by_item:
        return {"classified": 0, "note": "no outbound movements in window"}

    sorted_items = sorted(
        value_by_item.items(), key=lambda kv: kv[1], reverse=True
    )
    total_value = sum(v for _, v in sorted_items)
    cumulative = Decimal("0")
    classes: dict[int, ABCClass] = {}
    for item_id, val in sorted_items:
        cumulative += val
        ratio = cumulative / total_value if total_value > 0 else Decimal("0")
        if ratio <= Decimal("0.80"):
            classes[item_id] = ABCClass.A
        elif ratio <= Decimal("0.95"):
            classes[item_id] = ABCClass.B
        else:
            classes[item_id] = ABCClass.C

    now = _dt2.utcnow()
    for item_id, cls in classes.items():
        pol = (
            db.query(ItemPolicy)
            .filter(ItemPolicy.item_id == item_id)
            .with_for_update()
            .first()
        )
        if not pol:
            pol = ItemPolicy(item_id=item_id)
            db.add(pol)
            db.flush()
        pol.abc_class = cls
        pol.last_classified_at = now
    db.commit()
    return {
        "classified": len(classes),
        "A": sum(1 for c in classes.values() if c == ABCClass.A),
        "B": sum(1 for c in classes.values() if c == ABCClass.B),
        "C": sum(1 for c in classes.values() if c == ABCClass.C),
        "window_days": days,
    }


@router.get("/reorder-suggestions")
def reorder_suggestions(db: Session = Depends(get_db)):
    """Items whose on-hand stock is at or below reorder_point. Returns the
    suggested reorder_qty plus preferred_supplier so a buyer can convert to PO."""
    rows = (
        db.query(ItemPolicy, Item)
        .join(Item, Item.id == ItemPolicy.item_id)
        .filter(
            ItemPolicy.reorder_point > 0,
            Item.stock_qty <= ItemPolicy.reorder_point,
        )
        .all()
    )
    out = []
    for pol, item in rows:
        out.append(
            {
                "item_id": item.id,
                "sku": item.sku,
                "name": item.name,
                "stock_qty": float(item.stock_qty),
                "reorder_point": float(pol.reorder_point),
                "safety_stock": float(pol.safety_stock),
                "suggested_qty": float(pol.reorder_qty),
                "preferred_supplier_id": pol.preferred_supplier_id,
                "abc_class": pol.abc_class.value if pol.abc_class else None,
            }
        )
    return out


@router.post(
    "/auto-purchase-orders",
    dependencies=[Depends(_require_role("manager"))],
)
def auto_purchase_orders(db: Session = Depends(get_db)):
    """Generate one draft PO per supplier covering all under-stocked items
    they're the preferred source for. Items without preferred_supplier are
    skipped (returned in `unassigned`)."""
    from app.modules.suppliers.models import (
        POStatus,
        PurchaseOrder,
        PurchaseOrderItem,
    )

    suggestions = reorder_suggestions(db)
    by_supplier: dict[int, list[dict]] = {}
    unassigned: list[dict] = []
    for s in suggestions:
        if not s["preferred_supplier_id"] or s["suggested_qty"] <= 0:
            unassigned.append(s)
            continue
        by_supplier.setdefault(s["preferred_supplier_id"], []).append(s)

    created: list[dict] = []
    for sup_id, items in by_supplier.items():
        po_no = f"AUTO-{_dt2.utcnow().strftime('%Y%m%d%H%M%S')}-S{sup_id}"
        # Use unit_price = item.unit_price (sales price) as a placeholder when
        # supplier-specific cost isn't tracked; ops can edit before sending.
        item_ids = [s["item_id"] for s in items]
        item_rows = {
            i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()
        }
        total = Decimal("0")
        po = PurchaseOrder(
            po_no=po_no,
            supplier_id=sup_id,
            status=POStatus.draft,
            notes="Auto-generated from reorder suggestions",
        )
        for s in items:
            it = item_rows.get(s["item_id"])
            if not it:
                continue
            qty = Decimal(str(s["suggested_qty"]))
            price = Decimal(it.unit_price or 0)
            po.items.append(
                PurchaseOrderItem(
                    item_id=it.id, quantity=qty, unit_price=price
                )
            )
            total += qty * price
        po.total = total
        db.add(po)
        db.flush()
        created.append(
            {"po_id": po.id, "po_no": po_no, "supplier_id": sup_id, "lines": len(items)}
        )

    db.commit()
    return {"created": created, "unassigned": unassigned}
