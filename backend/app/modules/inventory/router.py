from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.modules.inventory import service
from app.modules.inventory.schemas import (
    ItemCreate,
    ItemOut,
    StockMovementCreate,
    StockMovementOut,
)

router = APIRouter(
    prefix="/api/inventory",
    tags=["inventory"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/items", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)):
    return service.list_items(db)


@router.post("/items", response_model=ItemOut)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    return service.create_item(db, payload)


@router.get("/movements", response_model=list[StockMovementOut])
def list_movements(db: Session = Depends(get_db)):
    return service.list_movements(db)


@router.post("/movements", response_model=StockMovementOut)
def create_movement(payload: StockMovementCreate, db: Session = Depends(get_db)):
    try:
        return service.create_movement(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
