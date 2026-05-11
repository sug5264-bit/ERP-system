"""Lease lifecycle: create → activate (compute PV + generate schedule) →
per-period posting (interest + depreciation)."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.lease.models import (
    Lease,
    LeaseScheduleEntry,
    LeaseStatus,
)


router = APIRouter(
    prefix="/api/lease",
    tags=["lease"],
    dependencies=[Depends(get_current_internal_user)],
)


class LeaseIn(BaseModel):
    lease_no: str
    description: str
    start_date: date
    end_date: date
    monthly_payment: Decimal
    annual_discount_rate: Decimal = Decimal("0.05")
    initial_direct_costs: Decimal = Decimal("0")
    counterparty: str | None = None
    notes: str | None = None


class LeaseOut(LeaseIn):
    id: int
    rou_asset: Decimal
    lease_liability: Decimal
    accumulated_depreciation: Decimal
    status: LeaseStatus
    model_config = ConfigDict(from_attributes=True)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.get("", response_model=list[LeaseOut])
def list_leases(status: LeaseStatus | None = None, db: Session = Depends(get_db)):
    q = db.query(Lease).order_by(Lease.start_date.desc())
    if status:
        q = q.filter(Lease.status == status)
    return q.all()


@router.post(
    "",
    response_model=LeaseOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_lease(payload: LeaseIn, db: Session = Depends(get_db)):
    if payload.end_date <= payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    if payload.monthly_payment <= 0:
        raise HTTPException(status_code=400, detail="monthly_payment must be > 0")
    if db.query(Lease).filter(Lease.lease_no == payload.lease_no).first():
        raise HTTPException(status_code=400, detail="lease_no exists")
    l = Lease(**payload.model_dump())
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


@router.post(
    "/{lease_id}/activate",
    response_model=LeaseOut,
    dependencies=[Depends(require_role("admin"))],
)
def activate_lease(lease_id: int, db: Session = Depends(get_db)):
    """Compute initial PV of payments and generate the amortization schedule.

    PV = sum(monthly_payment / (1+r/12)^n) for n=1..N.
    ROU asset = PV + initial_direct_costs.
    """
    l = db.query(Lease).filter(Lease.id == lease_id).with_for_update().first()
    if not l:
        raise HTTPException(status_code=404, detail="Not found")
    if l.status != LeaseStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot activate {l.status.value}")

    n = _months_between(l.start_date, l.end_date)
    if n < 1:
        raise HTTPException(status_code=400, detail="lease duration < 1 month")

    monthly_rate = Decimal(l.annual_discount_rate) / Decimal("12")
    payment = Decimal(l.monthly_payment)
    # Compute PV
    pv = Decimal("0")
    factor = Decimal("1")
    for i in range(1, n + 1):
        factor = factor * (Decimal("1") + monthly_rate)
        pv += payment / factor
    pv = _q(pv)

    l.lease_liability = pv
    l.rou_asset = _q(pv + Decimal(l.initial_direct_costs))
    l.status = LeaseStatus.active

    # Generate amortization schedule
    db.query(LeaseScheduleEntry).filter(LeaseScheduleEntry.lease_id == l.id).delete(
        synchronize_session=False
    )
    monthly_dep = _q(l.rou_asset / Decimal(n))
    opening = pv
    cur_year, cur_month = l.start_date.year, l.start_date.month
    for seq in range(1, n + 1):
        interest = _q(opening * monthly_rate)
        principal = _q(payment - interest)
        closing = _q(opening - principal)
        period_code = f"{cur_year}-{cur_month:02d}"
        db.add(LeaseScheduleEntry(
            lease_id=l.id, period_code=period_code, sequence=seq,
            opening_liability=opening, interest_expense=interest,
            payment=payment, principal=principal, closing_liability=closing,
            depreciation=monthly_dep,
        ))
        opening = closing
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    db.commit()
    db.refresh(l)
    return l


@router.get("/{lease_id}/schedule")
def lease_schedule(lease_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(LeaseScheduleEntry)
        .filter(LeaseScheduleEntry.lease_id == lease_id)
        .order_by(LeaseScheduleEntry.sequence)
        .all()
    )
    return [
        {
            "id": r.id, "period_code": r.period_code, "sequence": r.sequence,
            "opening_liability": float(r.opening_liability),
            "interest_expense": float(r.interest_expense),
            "payment": float(r.payment),
            "principal": float(r.principal),
            "closing_liability": float(r.closing_liability),
            "depreciation": float(r.depreciation),
            "posted": r.posted,
            "journal_entry_id": r.journal_entry_id,
        }
        for r in rows
    ]


@router.post(
    "/{lease_id}/post-period",
    dependencies=[Depends(require_role("admin"))],
)
def post_period(lease_id: int, period_code: str, db: Session = Depends(get_db)):
    """Post a single month's schedule:
      Dr 사용권자산상각비 / Cr 사용권자산-감가누계
      Dr 이자비용 + Dr 리스부채 / Cr 현금
    Marks the entry posted to prevent double-booking."""
    l = db.query(Lease).filter(Lease.id == lease_id).with_for_update().first()
    if not l:
        raise HTTPException(status_code=404, detail="Lease not found")
    if l.status != LeaseStatus.active:
        raise HTTPException(status_code=400, detail=f"Lease is {l.status.value}")
    sched = (
        db.query(LeaseScheduleEntry)
        .filter(
            LeaseScheduleEntry.lease_id == lease_id,
            LeaseScheduleEntry.period_code == period_code,
        )
        .with_for_update()
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule row not found for period")
    if sched.posted:
        raise HTTPException(status_code=400, detail="Already posted")

    # Best-effort GL post — requires accounts 1500 ROU, 1590 ROU 감가누계,
    # 2200 리스부채, 5210 이자비용, 5220 사용권 상각비, 1100 현금
    from app.modules.finance.models import Account, JournalEntry, JournalLine

    code_to_acc = {
        a.code: a
        for a in db.query(Account)
        .filter(Account.code.in_(["1100", "1500", "1590", "2200", "5210", "5220"]))
        .all()
    }
    je_id: int | None = None
    if all(c in code_to_acc for c in ("1100", "1590", "2200", "5210", "5220")):
        je = JournalEntry(
            entry_date=date(int(period_code[:4]), int(period_code[5:]), 1),
            description=f"Lease {l.lease_no} {period_code}",
            reference=f"LEASE-{l.lease_no}-{period_code}",
        )
        # Depreciation: Dr 5220 / Cr 1590
        je.lines.append(JournalLine(account_id=code_to_acc["5220"].id,
                                       debit=sched.depreciation, credit=Decimal("0")))
        je.lines.append(JournalLine(account_id=code_to_acc["1590"].id,
                                       debit=Decimal("0"), credit=sched.depreciation))
        # Payment: Dr 5210 (interest) + Dr 2200 (principal) / Cr 1100 (cash)
        je.lines.append(JournalLine(account_id=code_to_acc["5210"].id,
                                       debit=sched.interest_expense, credit=Decimal("0")))
        je.lines.append(JournalLine(account_id=code_to_acc["2200"].id,
                                       debit=sched.principal, credit=Decimal("0")))
        je.lines.append(JournalLine(account_id=code_to_acc["1100"].id,
                                       debit=Decimal("0"), credit=sched.payment))
        db.add(je)
        db.flush()
        je_id = je.id

    sched.posted = True
    sched.journal_entry_id = je_id
    l.lease_liability = Decimal(sched.closing_liability)
    l.accumulated_depreciation = Decimal(l.accumulated_depreciation) + Decimal(sched.depreciation)
    db.commit()
    return {
        "period_code": period_code,
        "interest_expense": float(sched.interest_expense),
        "principal": float(sched.principal),
        "depreciation": float(sched.depreciation),
        "journal_entry_id": je_id,
        "remaining_liability": float(l.lease_liability),
    }
