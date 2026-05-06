"""GraphQL gateway exposing read-only views over key business modules.

Auth is enforced via the existing JWT — pass `Authorization: Bearer <token>`
on the GraphQL request.
"""
from typing import Optional

import strawberry
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.core.auth import get_current_user
from app.core.db import get_db


@strawberry.type
class Employee:
    id: int
    employee_no: str
    full_name: str
    email: str
    position: Optional[str]


@strawberry.type
class Item:
    id: int
    sku: str
    name: str
    unit: str
    unit_price: float
    stock_qty: float


@strawberry.type
class Customer:
    id: int
    name: str
    company: Optional[str]
    email: Optional[str]


@strawberry.type
class Order:
    id: int
    order_no: str
    status: str
    total: float


@strawberry.type
class Query:
    @strawberry.field
    def employees(self, info: strawberry.Info) -> list[Employee]:
        from app.modules.hr.models import Employee as EmpModel

        db: Session = info.context["db"]
        return [
            Employee(
                id=e.id,
                employee_no=e.employee_no,
                full_name=e.full_name,
                email=e.email,
                position=e.position,
            )
            for e in db.query(EmpModel).all()
        ]

    @strawberry.field
    def items(self, info: strawberry.Info) -> list[Item]:
        from app.modules.inventory.models import Item as ItemModel

        db: Session = info.context["db"]
        return [
            Item(
                id=i.id,
                sku=i.sku,
                name=i.name,
                unit=i.unit,
                unit_price=float(i.unit_price),
                stock_qty=float(i.stock_qty),
            )
            for i in db.query(ItemModel).all()
        ]

    @strawberry.field
    def customers(self, info: strawberry.Info) -> list[Customer]:
        from app.modules.sales.models import Customer as CustModel

        db: Session = info.context["db"]
        return [
            Customer(id=c.id, name=c.name, company=c.company, email=c.email)
            for c in db.query(CustModel).all()
        ]

    @strawberry.field
    def orders(self, info: strawberry.Info) -> list[Order]:
        from app.modules.sales.models import SalesOrder

        db: Session = info.context["db"]
        return [
            Order(
                id=o.id,
                order_no=o.order_no,
                status=o.status.value if hasattr(o.status, "value") else str(o.status),
                total=float(o.total),
            )
            for o in db.query(SalesOrder).all()
        ]


schema = strawberry.Schema(query=Query)


async def get_context(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="auth required")
    return {"db": db, "user": user}


graphql_router = GraphQLRouter(schema, context_getter=get_context)
