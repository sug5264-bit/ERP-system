from app.core.time import utc_now
"""Admin-only operational endpoints: backup / restore / Excel import."""
import io
import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_role
from app.core.db import Base, engine, get_db

router = APIRouter(
    prefix="/api/admin",
    tags=["admin_ops"],
    dependencies=[Depends(require_role("admin"))],
)


# ---- Backup / Restore -------------------------------------------------------


def _serialise(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return value


@router.get("/backup")
def backup(db: Session = Depends(get_db)):
    """Dump every table to a JSON document, downloadable file."""
    payload: dict[str, list[dict]] = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(text(f"SELECT * FROM {table.name}")).mappings().all()
        payload[table.name] = [
            {k: _serialise(v) for k, v in row.items()} for row in rows
        ]

    body = json.dumps(
        {"exported_at": utc_now().isoformat(), "tables": payload},
        ensure_ascii=False,
        indent=2,
    )
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        iter([body.encode("utf-8")]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="erp-backup-{stamp}.json"'},
    )


@router.post("/restore")
async def restore(
    file: UploadFile = File(...),
    truncate_first: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Restore from a backup file. With truncate_first=true, wipes existing data first."""
    raw = await file.read()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid backup file: {exc}")

    if not isinstance(doc, dict) or "tables" not in doc:
        raise HTTPException(status_code=400, detail="Invalid backup format")

    tables = doc["tables"]
    inserted = 0

    if truncate_first:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f"DELETE FROM {table.name}"))

    for table in Base.metadata.sorted_tables:
        rows = tables.get(table.name)
        if not rows:
            continue
        for row in rows:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            try:
                db.execute(
                    text(f"INSERT INTO {table.name} ({cols}) VALUES ({placeholders})"),
                    row,
                )
                inserted += 1
            except Exception:
                # Skip rows that conflict; surface count instead of failing whole restore.
                continue

    db.commit()
    return {"tables": list(tables.keys()), "rows_inserted": inserted}


# ---- Excel import -----------------------------------------------------------


def _import_items(db: Session, ws) -> int:
    from app.modules.inventory.models import Item

    headers = [str(c.value).strip() if c.value else "" for c in ws[1]]
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(headers, row))
        sku = record.get("sku") or record.get("SKU")
        name = record.get("name") or record.get("품목명")
        if not sku or not name:
            continue
        existing = db.query(Item).filter(Item.sku == str(sku)).first()
        if existing:
            continue
        db.add(
            Item(
                sku=str(sku),
                name=str(name),
                unit=str(record.get("unit") or record.get("단위") or "EA"),
                unit_price=Decimal(str(record.get("unit_price") or record.get("단가") or 0)),
                stock_qty=Decimal(str(record.get("stock_qty") or record.get("재고") or 0)),
            )
        )
        count += 1
    return count


def _import_customers(db: Session, ws) -> int:
    from app.modules.sales.models import Customer

    headers = [str(c.value).strip() if c.value else "" for c in ws[1]]
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(headers, row))
        name = record.get("name") or record.get("이름")
        if not name:
            continue
        db.add(
            Customer(
                name=str(name),
                email=record.get("email"),
                phone=record.get("phone"),
                company=record.get("company") or record.get("회사"),
            )
        )
        count += 1
    return count


def _import_employees(db: Session, ws) -> int:
    from app.modules.hr.models import Employee

    headers = [str(c.value).strip() if c.value else "" for c in ws[1]]
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(headers, row))
        emp_no = record.get("employee_no") or record.get("사번")
        name = record.get("full_name") or record.get("이름")
        email = record.get("email") or record.get("이메일")
        if not emp_no or not name or not email:
            continue
        if db.query(Employee).filter(Employee.employee_no == str(emp_no)).first():
            continue
        db.add(
            Employee(
                employee_no=str(emp_no),
                full_name=str(name),
                email=str(email),
                position=record.get("position") or record.get("직책"),
                salary=Decimal(str(record.get("salary") or record.get("급여") or 0)),
            )
        )
        count += 1
    return count


IMPORT_HANDLERS = {
    "items": _import_items,
    "customers": _import_customers,
    "employees": _import_employees,
}


@router.post("/import")
async def import_excel(
    entity: str = Query(..., pattern="^(items|customers|employees)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import an .xlsx file. First row must be column headers (Korean or English)."""
    from openpyxl import load_workbook

    raw = await file.read()
    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read xlsx: {exc}")

    ws = wb.active
    handler = IMPORT_HANDLERS[entity]
    count = handler(db, ws)
    db.commit()
    return {"entity": entity, "imported": count}
