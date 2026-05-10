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


class ItemUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None


class StockLotUpdate(BaseModel):
    lot_number: str | None = None
    expiry_date: date | None = None
    supplier: str | None = None
    serial_number: str | None = None


class ItemOut(ItemBase):
    id: int
    stock_qty: Decimal

    model_config = ConfigDict(from_attributes=True)


class WarehouseIn(BaseModel):
    code: str
    name: str
    location: str | None = None


class WarehouseOut(WarehouseIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


class WarehouseStockOut(BaseModel):
    item_id: int
    warehouse_id: int
    quantity: Decimal
    avg_cost: Decimal

    model_config = ConfigDict(from_attributes=True)


class StockMovementCreate(BaseModel):
    item_id: int
    lot_id: int | None = None
    warehouse_id: int | None = None
    type: MovementType
    quantity: Decimal
    unit_cost: Decimal | None = None  # required on inbound; ignored on others
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
