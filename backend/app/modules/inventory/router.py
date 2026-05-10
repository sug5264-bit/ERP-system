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
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
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
