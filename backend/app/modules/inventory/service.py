from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.inventory.models import Item, MovementType, StockLot, StockMovement
from app.modules.inventory.schemas import ItemCreate, StockLotIn, StockMovementCreate


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

    lot: StockLot | None = None
    if payload.lot_id:
        lot = db.query(StockLot).filter(StockLot.id == payload.lot_id, StockLot.item_id == item.id).first()
        if not lot:
            raise ValueError("Lot not found for this item")

    qty = Decimal(payload.quantity)
    if payload.type == MovementType.inbound:
        item.stock_qty = Decimal(item.stock_qty) + qty
        if lot:
            lot.quantity = Decimal(lot.quantity) + qty
    elif payload.type == MovementType.outbound:
        if Decimal(item.stock_qty) < qty:
            raise ValueError("Insufficient stock")
        if lot and Decimal(lot.quantity) < qty:
            raise ValueError("Insufficient lot quantity")
        item.stock_qty = Decimal(item.stock_qty) - qty
        if lot:
            lot.quantity = Decimal(lot.quantity) - qty
    else:  # adjustment - quantity is the new absolute value
        item.stock_qty = qty
        if lot:
            lot.quantity = qty

    movement = StockMovement(**payload.model_dump())
    db.add(movement)
    db.commit()
    db.refresh(movement)

    # Append a tamper-evident ledger entry for supply-chain traceability.
    try:
        from app.modules.ledger import service as ledger_service

        ledger_service.append(
            db,
            event_type=f"stock_{payload.type.value}",
            resource_type="item",
            resource_id=item.id,
            payload={
                "movement_id": movement.id,
                "sku": item.sku,
                "quantity": float(qty),
                "lot_id": payload.lot_id,
                "new_stock_qty": float(item.stock_qty),
            },
        )
    except Exception:
        pass

    return movement


def list_lots(db: Session, item_id: int) -> list[StockLot]:
    return (
        db.query(StockLot)
        .filter(StockLot.item_id == item_id)
        .order_by(StockLot.lot_number)
        .all()
    )


def create_lot(db: Session, item_id: int, payload: StockLotIn) -> StockLot:
    if not get_item(db, item_id):
        raise ValueError("Item not found")
    lot = StockLot(item_id=item_id, **payload.model_dump())
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


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
