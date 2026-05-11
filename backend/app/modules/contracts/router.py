"""Contract CRUD + renewal-due alerts."""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.contracts.models import (
    Contract,
    ContractStatus,
    ContractType,
    RenewalType,
)

router = APIRouter(
    prefix="/api/contracts",
    tags=["contracts"],
    dependencies=[Depends(get_current_internal_user)],
)


class ContractIn(BaseModel):
    contract_no: str
    title: str
    type: ContractType
    counterparty: str
    customer_id: int | None = None
    supplier_id: int | None = None
    employee_id: int | None = None
    start_date: date
    end_date: date
    value: Decimal = Decimal("0")
    currency: str = "KRW"
    payment_terms: str | None = None
    renewal: RenewalType = RenewalType.manual
    notice_period_days: int = 30
    sla_response_hours: int | None = None
    notes: str | None = None
    document_url: str | None = None


class ContractOut(ContractIn):
    id: int
    status: ContractStatus
    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=Page[ContractOut])
def list_contracts(
    type: ContractType | None = None,
    status: ContractStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Contract).order_by(Contract.end_date.asc())
    if type:
        q = q.filter(Contract.type == type)
    if status:
        q = q.filter(Contract.status == status)
    return paginate(q, params)


@router.post(
    "",
    response_model=ContractOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_contract(payload: ContractIn, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date < start_date")
    if db.query(Contract).filter(Contract.contract_no == payload.contract_no).first():
        raise HTTPException(status_code=400, detail="contract_no exists")
    c = Contract(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.post(
    "/{cid}/activate",
    response_model=ContractOut,
    dependencies=[Depends(require_role("manager"))],
)
def activate_contract(cid: int, db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.id == cid).with_for_update().first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    if c.status != ContractStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot activate {c.status.value}")
    c.status = ContractStatus.active
    db.commit()
    db.refresh(c)
    return c


@router.post(
    "/{cid}/terminate",
    response_model=ContractOut,
    dependencies=[Depends(require_role("admin"))],
)
def terminate_contract(cid: int, reason: str | None = None, db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.id == cid).with_for_update().first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    c.status = ContractStatus.terminated
    if reason:
        c.notes = (c.notes or "") + f"\n[terminated] {reason}"
    db.commit()
    db.refresh(c)
    return c


@router.get("/renewals-due")
def renewals_due(within_days: int = 60, db: Session = Depends(get_db)):
    """Active contracts whose end_date is within `within_days` AND the
    notice_period_days window has started."""
    today = date.today()
    horizon = today + timedelta(days=within_days)
    rows = (
        db.query(Contract)
        .filter(
            Contract.status == ContractStatus.active,
            Contract.end_date <= horizon,
            Contract.end_date >= today,
        )
        .order_by(Contract.end_date.asc())
        .all()
    )
    out = []
    for c in rows:
        notice_starts = c.end_date - timedelta(days=c.notice_period_days)
        days_to_end = (c.end_date - today).days
        out.append({
            "id": c.id, "contract_no": c.contract_no, "title": c.title,
            "type": c.type.value, "counterparty": c.counterparty,
            "end_date": c.end_date.isoformat(),
            "renewal": c.renewal.value,
            "days_to_end": days_to_end,
            "in_notice_window": today >= notice_starts,
            "value": float(c.value),
        })
    return {"as_of": today.isoformat(), "within_days": within_days, "contracts": out}


@router.post(
    "/expire-overdue",
    dependencies=[Depends(require_role("admin"))],
)
def expire_overdue(db: Session = Depends(get_db)):
    """Cron entry: move active-but-past-end_date contracts to expired.
    Auto-renewal contracts get their end_date pushed by the same duration."""
    today = date.today()
    rows = (
        db.query(Contract)
        .filter(
            Contract.status == ContractStatus.active,
            Contract.end_date < today,
        )
        .with_for_update()
        .all()
    )
    expired = 0
    renewed = 0
    for c in rows:
        duration = (c.end_date - c.start_date).days or 365
        if c.renewal == RenewalType.auto:
            c.start_date = c.end_date
            c.end_date = c.end_date + timedelta(days=duration)
            renewed += 1
        else:
            c.status = ContractStatus.expired
            expired += 1
    db.commit()
    return {"expired": expired, "auto_renewed": renewed, "checked_at": today.isoformat()}
