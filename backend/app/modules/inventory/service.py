from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.inventory.models import Item, MovementType, StockMovement
from app.modules.inventory.schemas import ItemCreate, StockMovementCreate


def list_items(db: Session) -> list[Item]:
    return db.query(Item).order_by(Item.sku).all()


def get_item(db: Session, item_id: int) -> Item | None:
    return db.query(Item).filter(Item.id == item_id).first()


def create_item(db: Session, payload: ItemCreate) -> Item:
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_movements(db: Session) -> list[StockMovement]:
    return db.query(StockMovement).order_by(StockMovement.moved_at.desc()).all()


def create_movement(db: Session, payload: StockMovementCreate) -> StockMovement:
    item = get_item(db, payload.item_id)
    if not item:
        raise ValueError("Item not found")

    qty = Decimal(payload.quantity)
    if payload.type == MovementType.inbound:
        item.stock_qty = Decimal(item.stock_qty) + qty
    elif payload.type == MovementType.outbound:
        if Decimal(item.stock_qty) < qty:
            raise ValueError("Insufficient stock")
        item.stock_qty = Decimal(item.stock_qty) - qty
    else:  # adjustment - quantity is the new absolute value
        item.stock_qty = qty

    movement = StockMovement(**payload.model_dump())
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def adjust_stock_for_sale(db: Session, item_id: int, quantity: Decimal) -> None:
    """Helper used by sales module to deduct stock when an order is confirmed."""
    create_movement(
        db,
        StockMovementCreate(
            item_id=item_id,
            type=MovementType.outbound,
            quantity=quantity,
            note="Sales order",
        ),
    )
