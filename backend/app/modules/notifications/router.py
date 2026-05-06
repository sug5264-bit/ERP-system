from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.modules.inventory.models import Item
from app.modules.sales.models import OrderStatus, SalesOrder

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_notifications(
    low_stock_threshold: int = Query(10, ge=0),
    db: Session = Depends(get_db),
):
    """Compute alerts from current state. No persistence layer in PoC."""
    notifications: list[dict] = []

    low_stock_items = (
        db.query(Item).filter(Item.stock_qty < low_stock_threshold).order_by(Item.stock_qty).all()
    )
    for item in low_stock_items:
        qty = Decimal(item.stock_qty)
        notifications.append(
            {
                "id": f"low-stock-{item.id}",
                "level": "warning" if qty > 0 else "error",
                "type": "low_stock",
                "title": f"재고 부족: {item.name}",
                "message": f"SKU {item.sku} 재고가 {qty}로 임계치({low_stock_threshold}) 미만입니다.",
                "module": "inventory",
                "ref_id": item.id,
            }
        )

    open_orders = (
        db.query(SalesOrder)
        .filter(SalesOrder.status == OrderStatus.draft)
        .order_by(SalesOrder.order_date.desc())
        .all()
    )
    for order in open_orders:
        notifications.append(
            {
                "id": f"draft-order-{order.id}",
                "level": "info",
                "type": "draft_order",
                "title": f"미확정 주문: {order.order_no}",
                "message": f"주문 {order.order_no} 가 아직 확정되지 않았습니다.",
                "module": "sales",
                "ref_id": order.id,
            }
        )

    return {
        "count": len(notifications),
        "items": notifications,
    }
