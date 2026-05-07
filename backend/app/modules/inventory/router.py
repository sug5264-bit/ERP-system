from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_module_role
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.modules.inventory import service
from app.modules.inventory.models import Item, StockMovement
from app.modules.inventory.schemas import (
    ItemCreate,
    ItemOut,
    StockLotIn,
    StockLotOut,
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
def export_items(format: str = Query("csv"), db: Session = Depends(get_db)):
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
    return export_table(rows, headers, "items", format)


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
