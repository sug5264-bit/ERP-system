from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.modules.finance.models import Account, JournalLine
from app.modules.hr.models import Department, Employee
from app.modules.inventory.models import Item
from app.modules.sales.models import OrderStatus, SalesOrder

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return {
        "employees": db.query(func.count(Employee.id)).scalar() or 0,
        "items": db.query(func.count(Item.id)).scalar() or 0,
        "low_stock": db.query(func.count(Item.id)).filter(Item.stock_qty < 10).scalar() or 0,
        "orders": db.query(func.count(SalesOrder.id)).scalar() or 0,
        "open_orders": db.query(func.count(SalesOrder.id))
        .filter(SalesOrder.status == OrderStatus.draft)
        .scalar()
        or 0,
        "total_sales": float(
            db.query(func.coalesce(func.sum(SalesOrder.total), 0))
            .filter(SalesOrder.status != OrderStatus.cancelled)
            .scalar()
            or 0
        ),
    }


@router.get("/sales-by-month")
def sales_by_month(months: int = 6, db: Session = Depends(get_db)):
    """Confirmed sales totals per month for the last N months."""
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)

    rows = (
        db.query(SalesOrder.order_date, SalesOrder.total)
        .filter(SalesOrder.order_date >= start)
        .filter(SalesOrder.status != OrderStatus.cancelled)
        .all()
    )

    buckets: dict[str, Decimal] = {}
    cursor = start
    while cursor <= today:
        buckets[cursor.strftime("%Y-%m")] = Decimal("0")
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        cursor = next_month

    for order_date, total in rows:
        key = order_date.strftime("%Y-%m")
        if key in buckets:
            buckets[key] += Decimal(total)

    return [{"month": k, "total": float(v)} for k, v in sorted(buckets.items())]


@router.get("/employees-by-department")
def employees_by_department(db: Session = Depends(get_db)):
    rows = (
        db.query(Department.name, func.count(Employee.id))
        .outerjoin(Employee, Employee.department_id == Department.id)
        .group_by(Department.name)
        .all()
    )
    unassigned = (
        db.query(func.count(Employee.id)).filter(Employee.department_id.is_(None)).scalar() or 0
    )
    result = [{"department": name, "count": count} for name, count in rows]
    if unassigned:
        result.append({"department": "(미배정)", "count": unassigned})
    return result


@router.get("/top-items")
def top_items(limit: int = 5, db: Session = Depends(get_db)):
    """Top items by current stock value (qty * unit_price)."""
    items = db.query(Item).all()
    ranked = sorted(
        ({"sku": i.sku, "name": i.name, "value": float(Decimal(i.stock_qty) * Decimal(i.unit_price))} for i in items),
        key=lambda x: x["value"],
        reverse=True,
    )
    return ranked[:limit]


@router.get("/account-balances")
def account_balances(db: Session = Depends(get_db)):
    """Sum of (debit - credit) per account, grouped by account type."""
    rows = (
        db.query(
            Account.type,
            Account.code,
            Account.name,
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
        )
        .outerjoin(JournalLine, JournalLine.account_id == Account.id)
        .group_by(Account.id)
        .all()
    )
    return [
        {
            "type": acc_type.value if hasattr(acc_type, "value") else str(acc_type),
            "code": code,
            "name": name,
            "balance": float(balance),
        }
        for acc_type, code, name, balance in rows
    ]
