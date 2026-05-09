"""Admin-only operational endpoints: backup / restore / Excel import."""
from app.core.time import utc_now
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
from app.core.exports import _content_disposition

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


# Sensitive secret-like columns are scrubbed from backups so a JSON dump
# can't be used to exfiltrate hashed credentials.
SENSITIVE_COLUMNS: dict[str, set[str]] = {
    "users": {"hashed_password"},
    "api_keys": {"key_hash"},
    "refresh_tokens": {"token_hash"},
}


def _scrub(table_name: str, row: dict) -> dict:
    masked = SENSITIVE_COLUMNS.get(table_name, set())
    return {
        k: ("***REDACTED***" if k in masked else _serialise(v))
        for k, v in row.items()
    }


@router.get("/backup")
def backup(
    include_secrets: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Dump every table to a JSON document — streamed row-by-row.

    By default password / token hashes are redacted. Pass
    `include_secrets=true` only when restoring to the same instance.
    """
    try:
        schema_version = db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    except Exception:
        schema_version = None

    def stream_json():
        # Header
        yield (
            '{\n'
            f'  "exported_at": {json.dumps(utc_now().isoformat())},\n'
            f'  "schema_version": {json.dumps(schema_version)},\n'
            f'  "redacted": {json.dumps(not include_secrets)},\n'
            '  "tables": {\n'
        ).encode("utf-8")

        for t_idx, table in enumerate(Base.metadata.sorted_tables):
            sep = "," if t_idx > 0 else ""
            yield f"{sep}\n    {json.dumps(table.name)}: [".encode("utf-8")

            # Stream rows; yield_per cuts memory on large tables.
            cursor = db.execute(text(f"SELECT * FROM {table.name}")).yield_per(500)
            first = True
            for raw in cursor.mappings():
                obj = (
                    {k: _serialise(v) for k, v in raw.items()}
                    if include_secrets
                    else _scrub(table.name, dict(raw))
                )
                prefix = "" if first else ","
                first = False
                yield (prefix + "\n      " + json.dumps(obj, ensure_ascii=False)).encode("utf-8")

            yield b"\n    ]"

        yield b"\n  }\n}\n"

    body_iter = stream_json()
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        body_iter,
        media_type="application/json",
        headers={"Content-Disposition": _content_disposition(f"erp-backup-{stamp}.json")},
    )


@router.post("/restore")
async def restore(
    file: UploadFile = File(...),
    truncate_first: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Restore from a backup file.

    Security: column names from the uploaded JSON are validated against
    the actual table schema BEFORE any SQL is built — this stops a tampered
    backup from injecting SQL via crafted dict keys.
    """
    raw = await file.read()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid backup file: {exc}")

    if not isinstance(doc, dict) or "tables" not in doc:
        raise HTTPException(status_code=400, detail="Invalid backup format")

    # Refuse to restore a redacted dump — it would null-out password hashes.
    if doc.get("redacted") is True:
        raise HTTPException(
            status_code=400,
            detail="Refusing to restore a redacted backup. Re-export with include_secrets=true.",
        )

    # Validate alembic version matches — restoring across schema changes will
    # silently corrupt data.
    backup_version = doc.get("schema_version")
    try:
        current_version = db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    except Exception:
        current_version = None
    if backup_version and current_version and backup_version != current_version:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Backup is from schema {backup_version} but the running DB is "
                f"on {current_version}. Migrate one to match before restoring."
            ),
        )

    tables_payload = doc["tables"]
    # Build a {table_name: set(allowed_columns)} map from the actual schema.
    schema_columns = {
        t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables
    }
    inserted = 0

    if truncate_first:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f"DELETE FROM {table.name}"))

    for table in Base.metadata.sorted_tables:
        rows = tables_payload.get(table.name)
        if not rows:
            continue
        allowed = schema_columns[table.name]
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            # Drop unknown keys — both an injection guard and forward-compat.
            row = {k: v for k, v in raw_row.items() if k in allowed}
            if not row:
                continue
            cols = ", ".join(row.keys())  # safe: keys are from a static set
            placeholders = ", ".join(f":{k}" for k in row.keys())
            try:
                db.execute(
                    text(f"INSERT INTO {table.name} ({cols}) VALUES ({placeholders})"),
                    row,
                )
                inserted += 1
            except Exception:
                # Skip individual row conflicts; report aggregate count.
                continue

    db.commit()
    return {
        "tables": list(tables_payload.keys()),
        "rows_inserted": inserted,
        "schema_version": current_version,
    }


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
