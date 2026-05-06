from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.inventory.models import MovementType


class ItemBase(BaseModel):
    sku: str
    name: str
    unit: str = "EA"
    unit_price: Decimal = Decimal("0")


class ItemCreate(ItemBase):
    pass


class ItemOut(ItemBase):
    id: int
    stock_qty: Decimal

    class Config:
        from_attributes = True


class StockMovementCreate(BaseModel):
    item_id: int
    type: MovementType
    quantity: Decimal
    note: str | None = None


class StockMovementOut(BaseModel):
    id: int
    item_id: int
    type: MovementType
    quantity: Decimal
    moved_at: datetime
    note: str | None = None
    item: ItemOut | None = None

    class Config:
        from_attributes = True
