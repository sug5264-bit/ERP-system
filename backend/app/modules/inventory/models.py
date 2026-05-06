from datetime import date, datetime
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
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    stock_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)


class StockLot(BaseEntity):
    __tablename__ = "inv_lots"

    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False, index=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    supplier: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(200))

    item: Mapped[Item] = relationship()


class StockMovement(BaseEntity):
    __tablename__ = "inv_movements"

    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inv_lots.id"))
    type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    moved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(255))

    item: Mapped[Item] = relationship()
    lot: Mapped["StockLot | None"] = relationship()
