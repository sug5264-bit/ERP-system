from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_user, require_module_role
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.core.rls import can_access, scope_to_owner
from app.modules.auth.models import User
from app.modules.sales import service
from app.modules.sales.models import Customer, SalesOrder
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerOut,
    SalesOrderCreate,
    SalesOrderOut,
)
from app.modules.tenants.router import get_current_tenant_id

router = APIRouter(
    prefix="/api/sales",
    tags=["sales"],
    dependencies=[Depends(get_current_user)],
)


def _scoped_filter(user: User, tenant_id: int | None):
    """Apply both owner-RLS and tenant scoping to a query."""
    def apply(q, m):
        q = scope_to_owner(q, m, user, "sales")
        if tenant_id is not None:
            q = q.filter(m.tenant_id == tenant_id)
        return q
    return apply


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    q = _scoped_filter(user, tenant_id)(db.query(Customer), Customer).order_by(Customer.name)
    return paginate(q, params)


@router.post(
    "/customers",
    response_model=CustomerOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    return service.create_customer(db, payload, owner_id=user.id, tenant_id=tenant_id)


@router.get("/orders", response_model=Page[SalesOrderOut])
def list_orders(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    q = (
        _scoped_filter(user, tenant_id)(db.query(SalesOrder), SalesOrder)
        .options(selectinload(SalesOrder.customer), selectinload(SalesOrder.items))
        .order_by(SalesOrder.order_date.desc())
    )
    return paginate(q, params)


@router.get("/orders/export")
def export_orders(
    format: str = Query("csv"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    orders = service.list_orders(
        db, query_filter=lambda q, m: scope_to_owner(q, m, user, "sales")
    )
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
def create_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    return service.create_order(db, payload, owner_id=user.id, tenant_id=tenant_id)


@router.post(
    "/orders/{order_id}/confirm",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def confirm_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = service.get_order(db, order_id)
    if not order or not can_access(order, user, "sales"):
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        order = service.confirm_order(db, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return order
