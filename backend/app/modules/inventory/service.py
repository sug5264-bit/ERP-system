from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.inventory.models import (
    Item,
    MovementType,
    StockLot,
    StockMovement,
    Warehouse,
    WarehouseStock,
)
from app.modules.inventory.schemas import ItemCreate, StockLotIn, StockMovementCreate


def _adjust_warehouse_stock(
    db: Session,
    item_id: int,
    warehouse_id: int | None,
    type_: MovementType,
    qty: Decimal,
    unit_cost: Decimal | None,
) -> None:
    """Update per-warehouse on-hand and the moving-average cost.

    Skipped when no warehouse_id is given (legacy single-warehouse path).
    """
    if warehouse_id is None:
        return
    ws = (
        db.query(WarehouseStock)
        .filter(
            WarehouseStock.item_id == item_id,
            WarehouseStock.warehouse_id == warehouse_id,
        )
        .with_for_update()
        .first()
    )
    if not ws:
        ws = WarehouseStock(
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity=Decimal("0"),
            avg_cost=Decimal("0"),
        )
        db.add(ws)
        db.flush()

    cur_qty = Decimal(ws.quantity)
    cur_avg = Decimal(ws.avg_cost)

    if type_ == MovementType.inbound:
        cost = Decimal(unit_cost) if unit_cost is not None else cur_avg
        new_qty = cur_qty + qty
        if new_qty > 0:
            ws.avg_cost = ((cur_qty * cur_avg + qty * cost) / new_qty).quantize(
                Decimal("0.0001")
            )
        ws.quantity = new_qty
    elif type_ == MovementType.outbound:
        if cur_qty < qty:
            raise ValueError(
                f"Insufficient stock at warehouse {warehouse_id}: {cur_qty} < {qty}"
            )
        ws.quantity = cur_qty - qty
        # avg_cost unchanged on outbound
    else:  # adjustment — set absolute
        ws.quantity = qty


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
    # Lock the item row so concurrent movements serialize on it.
    # On Postgres this becomes SELECT ... FOR UPDATE; on SQLite it's a no-op
    # but the BEGIN IMMEDIATE transaction still serializes writers.
    item = (
        db.query(Item)
        .filter(Item.id == payload.item_id)
        .with_for_update()
        .first()
    )
    if not item:
        raise ValueError("Item not found")

    lot: StockLot | None = None
    if payload.lot_id:
        lot = (
            db.query(StockLot)
            .filter(StockLot.id == payload.lot_id, StockLot.item_id == item.id)
            .with_for_update()
            .first()
        )
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

    # Per-warehouse stock + moving-average cost (no-op when warehouse_id is None)
    _adjust_warehouse_stock(
        db,
        item_id=item.id,
        warehouse_id=payload.warehouse_id,
        type_=payload.type,
        qty=qty,
        unit_cost=payload.unit_cost,
    )

    movement = StockMovement(**payload.model_dump())
    db.add(movement)
    db.commit()
    db.refresh(movement)

    # Append a tamper-evident ledger entry for supply-chain traceability.
    # If this fails the movement still succeeds — but we surface it in logs.
    import logging

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
        logging.getLogger("erp.inventory").exception(
            "failed to append ledger entry for movement %s", movement.id
        )

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
