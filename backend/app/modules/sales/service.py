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


def create_customer(db: Session, payload: CustomerCreate, owner_id: int | None = None) -> Customer:
    customer = Customer(**payload.model_dump(), owner_id=owner_id)
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


def create_order(db: Session, payload: SalesOrderCreate, owner_id: int | None = None) -> SalesOrder:
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
    )
    for line in payload.items:
        order.items.append(SalesOrderItem(**line.model_dump()))
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def confirm_order(db: Session, order_id: int) -> SalesOrder | None:
    """Confirm an order and deduct stock for each line item."""
    order = get_order(db, order_id)
    if not order:
        return None
    if order.status != OrderStatus.draft:
        raise ValueError(f"Order is already {order.status.value}")

    for line in order.items:
        inventory_service.adjust_stock_for_sale(db, line.item_id, Decimal(line.quantity))

    order.status = OrderStatus.confirmed
    db.commit()
    db.refresh(order)
    return order
