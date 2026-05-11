"""Pre-built KPI registry. Each entry: code → callable(db, params) → result.

A KPI returns:
    { "value": number, "label": str, "unit": str, "breakdown": [...] }
where `breakdown` (optional) is a drill-down — list of {dimension, value}.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session


KPIFn = Callable[[Session, dict], dict]
_REGISTRY: dict[str, dict] = {}


def register(code: str, label: str, unit: str = "") -> Callable[[KPIFn], KPIFn]:
    def decorator(fn: KPIFn) -> KPIFn:
        _REGISTRY[code] = {"code": code, "label": label, "unit": unit, "fn": fn}
        return fn
    return decorator


def list_kpis() -> list[dict]:
    return [
        {"code": k["code"], "label": k["label"], "unit": k["unit"]}
        for k in _REGISTRY.values()
    ]


def run(code: str, db: Session, params: dict | None = None) -> dict:
    entry = _REGISTRY.get(code)
    if not entry:
        raise KeyError(code)
    result = entry["fn"](db, params or {})
    return {
        "code": entry["code"],
        "label": entry["label"],
        "unit": entry["unit"],
        **result,
    }


# ---- Built-in KPIs --------------------------------------------------------


@register("sales.total", "총 매출", "KRW")
def _sales_total(db: Session, params: dict) -> dict:
    from app.modules.sales.models import OrderStatus, SalesOrder

    days = int(params.get("days", 30))
    cutoff = date.today() - timedelta(days=days)
    total = (
        db.query(func.coalesce(func.sum(SalesOrder.total), 0))
        .filter(
            SalesOrder.status == OrderStatus.confirmed,
            SalesOrder.order_date >= cutoff,
        )
        .scalar()
        or 0
    )
    # Drill-down: by month
    rows = (
        db.query(
            func.strftime("%Y-%m", SalesOrder.order_date).label("month"),
            func.coalesce(func.sum(SalesOrder.total), 0).label("amount"),
        )
        .filter(
            SalesOrder.status == OrderStatus.confirmed,
            SalesOrder.order_date >= cutoff,
        )
        .group_by("month")
        .order_by("month")
        .all()
    )
    return {
        "value": float(total),
        "breakdown": [
            {"dimension": r.month, "value": float(r.amount)} for r in rows
        ],
    }


@register("sales.confirmed_orders", "확정 주문 수", "건")
def _confirmed_orders(db: Session, params: dict) -> dict:
    from app.modules.sales.models import OrderStatus, SalesOrder

    days = int(params.get("days", 30))
    cutoff = date.today() - timedelta(days=days)
    cnt = (
        db.query(func.count(SalesOrder.id))
        .filter(
            SalesOrder.status == OrderStatus.confirmed,
            SalesOrder.order_date >= cutoff,
        )
        .scalar()
        or 0
    )
    return {"value": int(cnt), "breakdown": []}


@register("inventory.low_stock", "재고 부족 품목 수", "건")
def _low_stock(db: Session, params: dict) -> dict:
    from app.modules.inventory.models import Item, ItemPolicy

    rows = (
        db.query(Item.id, Item.sku, Item.name, Item.stock_qty, ItemPolicy.reorder_point)
        .join(ItemPolicy, ItemPolicy.item_id == Item.id)
        .filter(
            ItemPolicy.reorder_point > 0,
            Item.stock_qty <= ItemPolicy.reorder_point,
        )
        .all()
    )
    return {
        "value": len(rows),
        "breakdown": [
            {"dimension": f"{r.sku} {r.name}", "value": float(r.stock_qty)}
            for r in rows
        ],
    }


@register("inventory.value", "재고 평가액", "KRW")
def _inventory_value(db: Session, params: dict) -> dict:
    from app.modules.inventory.models import Item

    rows = db.query(Item.sku, Item.name, Item.stock_qty, Item.unit_price).all()
    total = Decimal("0")
    breakdown = []
    for r in rows:
        val = Decimal(r.stock_qty) * Decimal(r.unit_price)
        if val > 0:
            total += val
            breakdown.append({"dimension": f"{r.sku} {r.name}", "value": float(val)})
    breakdown.sort(key=lambda x: x["value"], reverse=True)
    return {"value": float(total), "breakdown": breakdown[:20]}


@register("finance.ar_outstanding", "미수금 (외상매출)", "KRW")
def _ar(db: Session, params: dict) -> dict:
    from app.modules.billing.models import Invoice, InvoiceStatus

    rows = (
        db.query(Invoice.invoice_no, Invoice.total, Invoice.paid_amount)
        .filter(Invoice.status.in_([InvoiceStatus.issued, InvoiceStatus.partially_paid]))
        .all()
    )
    total = Decimal("0")
    breakdown = []
    for r in rows:
        outstanding = Decimal(r.total) - Decimal(r.paid_amount)
        if outstanding > 0:
            total += outstanding
            breakdown.append({"dimension": r.invoice_no, "value": float(outstanding)})
    breakdown.sort(key=lambda x: x["value"], reverse=True)
    return {"value": float(total), "breakdown": breakdown[:20]}


@register("hr.headcount", "직원 수", "명")
def _headcount(db: Session, params: dict) -> dict:
    from app.modules.hr.models import Department, Employee

    total = db.query(func.count(Employee.id)).scalar() or 0
    rows = (
        db.query(Department.name, func.count(Employee.id).label("c"))
        .outerjoin(Employee, Employee.department_id == Department.id)
        .group_by(Department.id)
        .all()
    )
    return {
        "value": int(total),
        "breakdown": [
            {"dimension": r.name, "value": int(r.c)} for r in rows
        ],
    }


@register("crm.pipeline_weighted", "파이프라인 가중 금액", "KRW")
def _pipeline(db: Session, params: dict) -> dict:
    from app.modules.crm.models import Opportunity, OpportunityStage

    rows = (
        db.query(
            Opportunity.stage,
            func.count(Opportunity.id).label("c"),
            func.coalesce(
                func.sum(Opportunity.amount * Opportunity.probability / 100), 0
            ).label("w"),
        )
        .filter(Opportunity.stage.notin_([OpportunityStage.won, OpportunityStage.lost]))
        .group_by(Opportunity.stage)
        .all()
    )
    total = sum((float(r.w) for r in rows), 0.0)
    return {
        "value": total,
        "breakdown": [
            {"dimension": r.stage.value, "value": float(r.w)} for r in rows
        ],
    }
