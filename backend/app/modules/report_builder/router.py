"""Report-builder runtime.

Available data sources are explicitly registered here as a whitelist —
no string-to-SQL conversion. Users define WHAT to read; the runtime maps
their spec to whitelisted columns + a safe set of aggregations and filters.
"""
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.report_builder.models import ReportDefinition

router = APIRouter(
    prefix="/api/report-builder",
    tags=["report_builder"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Whitelisted data sources ---------------------------------------------


def _data_sources() -> dict[str, dict]:
    """Map source name → ORM model + safe column whitelist.

    Imported lazily so model-import order doesn't matter.
    """
    from app.modules.finance.models import Account, JournalEntry
    from app.modules.hr.models import Employee
    from app.modules.inventory.models import Item, StockMovement
    from app.modules.sales.models import Customer, SalesOrder

    return {
        "items": {
            "model": Item,
            "columns": {
                "id": Item.id,
                "sku": Item.sku,
                "name": Item.name,
                "unit": Item.unit,
                "unit_price": Item.unit_price,
                "stock_qty": Item.stock_qty,
            },
        },
        "movements": {
            "model": StockMovement,
            "columns": {
                "id": StockMovement.id,
                "item_id": StockMovement.item_id,
                "type": StockMovement.type,
                "quantity": StockMovement.quantity,
                "moved_at": StockMovement.moved_at,
            },
        },
        "employees": {
            "model": Employee,
            "columns": {
                "id": Employee.id,
                "employee_no": Employee.employee_no,
                "full_name": Employee.full_name,
                "position": Employee.position,
                "salary": Employee.salary,
                "department_id": Employee.department_id,
            },
        },
        "customers": {
            "model": Customer,
            "columns": {
                "id": Customer.id,
                "name": Customer.name,
                "company": Customer.company,
                "email": Customer.email,
            },
        },
        "orders": {
            "model": SalesOrder,
            "columns": {
                "id": SalesOrder.id,
                "order_no": SalesOrder.order_no,
                "customer_id": SalesOrder.customer_id,
                "order_date": SalesOrder.order_date,
                "status": SalesOrder.status,
                "total": SalesOrder.total,
            },
        },
        "journal_entries": {
            "model": JournalEntry,
            "columns": {
                "id": JournalEntry.id,
                "entry_date": JournalEntry.entry_date,
                "description": JournalEntry.description,
                "reference": JournalEntry.reference,
            },
        },
        "accounts": {
            "model": Account,
            "columns": {
                "id": Account.id,
                "code": Account.code,
                "name": Account.name,
                "type": Account.type,
            },
        },
    }


_AGG_FUNCS = {
    "sum": func.sum,
    "avg": func.avg,
    "count": func.count,
    "min": func.min,
    "max": func.max,
}

_FILTER_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "like", "in"}


def _run(spec: dict, db: Session) -> dict:
    sources = _data_sources()
    src_name = spec.get("data_source")
    if src_name not in sources:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown data_source. Choose from: {list(sources)}",
        )
    src = sources[src_name]
    cols = src["columns"]

    # Build select expression list
    select_specs = spec.get("columns") or list(cols.keys())
    selected = []
    labels = []
    for c in select_specs:
        if isinstance(c, str):
            if c not in cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown column '{c}' for {src_name}. Allowed: {list(cols)}",
                )
            selected.append(cols[c].label(c))
            labels.append(c)
        elif isinstance(c, dict) and c.get("agg") in _AGG_FUNCS:
            col = c.get("column")
            if col not in cols:
                raise HTTPException(status_code=400, detail=f"Unknown column '{col}'")
            alias = c.get("alias") or f"{c['agg']}_{col}"
            selected.append(_AGG_FUNCS[c["agg"]](cols[col]).label(alias))
            labels.append(alias)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid column spec: {c!r}")

    q = db.query(*selected)

    # Filters
    for f in spec.get("filters") or []:
        col_name = f.get("column")
        op = f.get("op")
        val = f.get("value")
        if col_name not in cols or op not in _FILTER_OPS:
            raise HTTPException(status_code=400, detail=f"Bad filter: {f!r}")
        column = cols[col_name]
        if op == "eq":
            q = q.filter(column == val)
        elif op == "ne":
            q = q.filter(column != val)
        elif op == "gt":
            q = q.filter(column > val)
        elif op == "gte":
            q = q.filter(column >= val)
        elif op == "lt":
            q = q.filter(column < val)
        elif op == "lte":
            q = q.filter(column <= val)
        elif op == "like":
            q = q.filter(column.ilike(f"%{val}%"))
        elif op == "in":
            if not isinstance(val, list):
                raise HTTPException(status_code=400, detail="'in' value must be a list")
            q = q.filter(column.in_(val))

    # Group-by
    for g in spec.get("group_by") or []:
        if g not in cols:
            raise HTTPException(status_code=400, detail=f"Unknown group_by column '{g}'")
        q = q.group_by(cols[g])

    # Order-by
    for o in spec.get("order_by") or []:
        col_name = o.get("column")
        direction = (o.get("dir") or "asc").lower()
        if col_name not in cols:
            raise HTTPException(status_code=400, detail=f"Unknown order_by '{col_name}'")
        col = cols[col_name]
        q = q.order_by(col.desc() if direction == "desc" else col.asc())

    limit = min(int(spec.get("limit") or 1000), 5000)
    rows = q.limit(limit).all()
    # Convert to list[dict] using labels
    out_rows = []
    for r in rows:
        out_rows.append({lbl: getattr(r, lbl, None) for lbl in labels})
    return {"columns": labels, "rows": out_rows, "count": len(out_rows)}


# ---- Schemas ---------------------------------------------------------------


class ReportSpec(BaseModel):
    data_source: str
    columns: list[Any] | None = None
    filters: list[dict] | None = None
    group_by: list[str] | None = None
    order_by: list[dict] | None = None
    limit: int | None = None


class ReportDefIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    spec: ReportSpec
    is_public: bool = False


class ReportDefOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    spec: dict
    is_public: bool
    owner_id: int | None
    model_config = ConfigDict(from_attributes=True)


def _to_out(d: ReportDefinition) -> dict:
    return {
        "id": d.id,
        "code": d.code,
        "name": d.name,
        "description": d.description,
        "spec": json.loads(d.spec) if d.spec else {},
        "is_public": d.is_public,
        "owner_id": d.owner_id,
    }


# ---- Endpoints -------------------------------------------------------------


@router.get("/data-sources")
def list_data_sources():
    """Whitelisted data sources + columns for the UI builder."""
    return {
        name: list(src["columns"].keys())
        for name, src in _data_sources().items()
    }


@router.post("/run")
def run_inline(spec: ReportSpec, db: Session = Depends(get_db)):
    """Run an ad-hoc spec without persisting it."""
    return _run(spec.model_dump(exclude_none=True), db)


@router.get("/definitions", response_model=list[ReportDefOut])
def list_definitions(
    db: Session = Depends(get_db), user: User = Depends(get_current_internal_user)
):
    rows = (
        db.query(ReportDefinition)
        .filter(
            (ReportDefinition.is_public.is_(True))
            | (ReportDefinition.owner_id == user.id)
        )
        .order_by(ReportDefinition.code)
        .all()
    )
    return [_to_out(d) for d in rows]


@router.post("/definitions", response_model=ReportDefOut)
def create_definition(
    payload: ReportDefIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    if db.query(ReportDefinition).filter(ReportDefinition.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    # Validate spec by running it once with limit=0
    _run({**payload.spec.model_dump(exclude_none=True), "limit": 1}, db)
    d = ReportDefinition(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        spec=json.dumps(payload.spec.model_dump(exclude_none=True), ensure_ascii=False),
        owner_id=user.id,
        is_public=payload.is_public,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _to_out(d)


@router.get("/definitions/{def_id}/run")
def run_saved(
    def_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    d = db.query(ReportDefinition).filter(ReportDefinition.id == def_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Definition not found")
    if not d.is_public and d.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your private report")
    return _run(json.loads(d.spec), db)


@router.delete(
    "/definitions/{def_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_definition(def_id: int, db: Session = Depends(get_db)):
    d = db.query(ReportDefinition).filter(ReportDefinition.id == def_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(d)
    db.commit()
    return {"ok": True}
