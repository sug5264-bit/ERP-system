from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.base_model import BaseEntity


class MovementType(str, PyEnum):
    inbound = "inbound"
    outbound = "outbound"
    adjustment = "adjustment"


class Item(BaseEntity):
    __tablename__ = "inv_items"

    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="EA")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)


class Warehouse(BaseEntity):
    __tablename__ = "inv_warehouses"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500))


class WarehouseStock(BaseEntity):
    """Per-warehouse on-hand quantity + moving-average cost.

    On inbound: avg_cost = (old_qty * old_avg + qty * unit_cost) / new_qty
    On outbound / adjustment: avg_cost is unchanged (cost relieved at avg_cost).
    """

    __tablename__ = "inv_warehouse_stock"

    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("inv_warehouses.id"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))


class StockLot(BaseEntity):
    __tablename__ = "inv_lots"

    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False, index=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    supplier: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(200))

    item: Mapped[Item] = relationship()


class StockMovement(BaseEntity):
    __tablename__ = "inv_movements"

    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("inv_warehouses.id"))
    type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    moved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(255))

    item: Mapped[Item] = relationship()
    lot: Mapped["StockLot | None"] = relationship()


class ABCClass(str, PyEnum):
    A = "A"  # top 80% of value
    B = "B"  # next 15%
    C = "C"  # bottom 5%


class ItemPolicy(BaseEntity):
    """Stocking policy for a single item: reorder point + safety stock +
    classification. One row per item (uniqueness enforced)."""

    __tablename__ = "inv_item_policies"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("inv_items.id"), nullable=False, unique=True, index=True
    )
    reorder_point: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    reorder_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0")
    )
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    abc_class: Mapped[ABCClass | None] = mapped_column(Enum(ABCClass), index=True)
    last_classified_at: Mapped[datetime | None] = mapped_column(DateTime)
