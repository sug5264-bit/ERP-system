from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.modules.inventory.models import MovementType


class StockLotIn(BaseModel):
    lot_number: str
    quantity: Decimal = Decimal("0")
    expiry_date: date | None = None
    supplier: str | None = None
    serial_number: str | None = None


class StockLotOut(StockLotIn):
    id: int
    item_id: int

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class StockMovementCreate(BaseModel):
    item_id: int
    lot_id: int | None = None
    type: MovementType
    quantity: Decimal
    note: str | None = None


class StockMovementOut(BaseModel):
    id: int
    item_id: int
    lot_id: int | None = None
    type: MovementType
    quantity: Decimal
    moved_at: datetime
    note: str | None = None
    item: ItemOut | None = None

    model_config = ConfigDict(from_attributes=True)
