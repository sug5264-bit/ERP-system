from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Query, Session

from app.modules.inventory import service as inventory_service
from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem
from app.modules.sales.schemas import CustomerCreate, SalesOrderCreate


def list_customers(db: Session, query_filter=None) -> list[Customer]:
    q: Query = db.query(Customer)
    if query_filter is not None:
        q = query_filter(q, Customer)
    return q.order_by(Customer.name).all()


def create_customer(
    db: Session,
    payload: CustomerCreate,
    owner_id: int | None = None,
    tenant_id: int | None = None,
) -> Customer:
    customer = Customer(**payload.model_dump(), owner_id=owner_id, tenant_id=tenant_id)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def list_orders(db: Session, query_filter=None) -> list[SalesOrder]:
    q: Query = db.query(SalesOrder)
    if query_filter is not None:
        q = query_filter(q, SalesOrder)
    return q.order_by(SalesOrder.order_date.desc()).all()


def get_order(db: Session, order_id: int) -> SalesOrder | None:
    return db.query(SalesOrder).filter(SalesOrder.id == order_id).first()


def create_order(
    db: Session,
    payload: SalesOrderCreate,
    owner_id: int | None = None,
    tenant_id: int | None = None,
) -> SalesOrder:
    total = sum(
        (Decimal(line.quantity) * Decimal(line.unit_price) for line in payload.items),
        Decimal("0"),
    )
    order = SalesOrder(
        order_no=payload.order_no,
        customer_id=payload.customer_id,
        order_date=payload.order_date or date.today(),
        status=OrderStatus.draft,
        total=total,
        owner_id=owner_id,
        tenant_id=tenant_id,
    )
    for line in payload.items:
        order.items.append(SalesOrderItem(**line.model_dump()))
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def confirm_order(db: Session, order_id: int) -> SalesOrder | None:
    """Confirm an order and deduct stock for each line item.

    Pre-flight: lock + validate every line BEFORE any decrement happens, so a
    shortfall on line N doesn't leave earlier lines partially decremented.
    """
    from app.modules.inventory.models import Item

    order = get_order(db, order_id)
    if not order:
        return None
    if order.status != OrderStatus.draft:
        raise ValueError(f"Order is already {order.status.value}")

    # Pre-flight: lock all items in deterministic order to avoid deadlocks,
    # and verify there's enough stock for every line.
    item_ids = sorted({line.item_id for line in order.items})
    items_by_id = {
        i.id: i
        for i in db.query(Item)
        .filter(Item.id.in_(item_ids))
        .with_for_update()
        .all()
    }

    needed: dict[int, Decimal] = {}
    for line in order.items:
        needed[line.item_id] = needed.get(line.item_id, Decimal("0")) + Decimal(line.quantity)

    for item_id, qty in needed.items():
        item = items_by_id.get(item_id)
        if not item:
            raise ValueError(f"item {item_id} not found")
        if Decimal(item.stock_qty) < qty:
            raise ValueError(
                f"Insufficient stock for {item.sku}: have {item.stock_qty}, need {qty}"
            )

    # All checks passed — now apply the movements and accumulate cost.
    total_cost = Decimal("0")
    from app.modules.inventory.models import WarehouseStock

    for line in order.items:
        # Approximate COGS at the item's first warehouse avg_cost (if any).
        ws = (
            db.query(WarehouseStock)
            .filter(WarehouseStock.item_id == line.item_id)
            .order_by(WarehouseStock.id)
            .first()
        )
        if ws is not None:
            total_cost += Decimal(ws.avg_cost) * Decimal(line.quantity)
        inventory_service.adjust_stock_for_sale(db, line.item_id, Decimal(line.quantity))

    order.status = OrderStatus.confirmed
    db.flush()

    # Best-effort COGS posting (Dr COGS / Cr Inventory)
    if total_cost > 0:
        try:
            from app.modules.finance.auto_post import post_cogs

            post_cogs(db, order_no=order.order_no, cost=total_cost)
        except Exception:
            import logging

            logging.getLogger("erp.sales").exception(
                "auto-post COGS failed for order %s — order still confirmed",
                order.order_no,
            )

    db.commit()
    db.refresh(order)
    return order
