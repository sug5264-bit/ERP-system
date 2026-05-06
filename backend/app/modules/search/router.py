from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.modules.finance.models import Account, JournalEntry
from app.modules.hr.models import Department, Employee
from app.modules.inventory.models import Item
from app.modules.sales.models import Customer, SalesOrder

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def global_search(q: str = Query(..., min_length=1), limit: int = 5, db: Session = Depends(get_db)):
    """Cross-module ILIKE search. PoC-grade — replace with Postgres FTS or
    Meilisearch/Elasticsearch when scaling."""
    needle = f"%{q}%"
    results: list[dict] = []

    employees = (
        db.query(Employee)
        .filter(or_(Employee.full_name.ilike(needle), Employee.employee_no.ilike(needle), Employee.email.ilike(needle)))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "hr",
            "type": "employee",
            "id": e.id,
            "title": f"{e.full_name} ({e.employee_no})",
            "subtitle": e.email,
            "href": "/hr",
        }
        for e in employees
    )

    departments = db.query(Department).filter(Department.name.ilike(needle)).limit(limit).all()
    results.extend(
        {
            "module": "hr",
            "type": "department",
            "id": d.id,
            "title": d.name,
            "subtitle": d.description or "",
            "href": "/hr",
        }
        for d in departments
    )

    items = (
        db.query(Item)
        .filter(or_(Item.sku.ilike(needle), Item.name.ilike(needle)))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "inventory",
            "type": "item",
            "id": i.id,
            "title": f"{i.sku} - {i.name}",
            "subtitle": f"재고 {i.stock_qty}",
            "href": "/inventory",
        }
        for i in items
    )

    customers = (
        db.query(Customer)
        .filter(or_(Customer.name.ilike(needle), Customer.company.ilike(needle), Customer.email.ilike(needle)))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "sales",
            "type": "customer",
            "id": c.id,
            "title": c.name,
            "subtitle": c.company or c.email or "",
            "href": "/sales",
        }
        for c in customers
    )

    orders = (
        db.query(SalesOrder)
        .filter(SalesOrder.order_no.ilike(needle))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "sales",
            "type": "order",
            "id": o.id,
            "title": o.order_no,
            "subtitle": f"{o.status.value} / {o.total}",
            "href": "/sales",
        }
        for o in orders
    )

    accounts = (
        db.query(Account)
        .filter(or_(Account.code.ilike(needle), Account.name.ilike(needle)))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "finance",
            "type": "account",
            "id": a.id,
            "title": f"{a.code} {a.name}",
            "subtitle": a.type.value if hasattr(a.type, "value") else str(a.type),
            "href": "/finance",
        }
        for a in accounts
    )

    journals = (
        db.query(JournalEntry)
        .filter(or_(JournalEntry.description.ilike(needle), JournalEntry.reference.ilike(needle)))
        .limit(limit)
        .all()
    )
    results.extend(
        {
            "module": "finance",
            "type": "journal",
            "id": j.id,
            "title": j.description,
            "subtitle": j.reference or j.entry_date.isoformat(),
            "href": "/finance",
        }
        for j in journals
    )

    return {"query": q, "count": len(results), "results": results}
