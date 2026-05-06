from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_module_role
from app.core.db import get_db
from app.core.exports import export_table
from app.modules.sales import service
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerOut,
    SalesOrderCreate,
    SalesOrderOut,
)

router = APIRouter(
    prefix="/api/sales",
    tags=["sales"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return service.list_customers(db)


@router.post(
    "/customers",
    response_model=CustomerOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    return service.create_customer(db, payload)


@router.get("/orders", response_model=list[SalesOrderOut])
def list_orders(db: Session = Depends(get_db)):
    return service.list_orders(db)


@router.get("/orders/export")
def export_orders(format: str = Query("csv"), db: Session = Depends(get_db)):
    orders = service.list_orders(db)
    headers = ["주문번호", "일자", "고객", "상태", "총액"]
    rows = [
        [
            o.order_no,
            o.order_date.isoformat(),
            o.customer.name if o.customer else "",
            o.status.value if hasattr(o.status, "value") else str(o.status),
            float(o.total),
        ]
        for o in orders
    ]
    return export_table(rows, headers, "orders", format)


@router.post(
    "/orders",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_order(payload: SalesOrderCreate, db: Session = Depends(get_db)):
    return service.create_order(db, payload)


@router.post(
    "/orders/{order_id}/confirm",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def confirm_order(order_id: int, db: Session = Depends(get_db)):
    try:
        order = service.confirm_order(db, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
