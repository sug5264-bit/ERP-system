"""Consolidation + tax adjustments."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.consolidation.models import (
    EliminationEntry,
    EliminationType,
    TaxAdjustment,
)
from app.modules.finance.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalLine,
)

router = APIRouter(
    prefix="/api/consolidation",
    tags=["consolidation"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class EliminationIn(BaseModel):
    period_code: str
    type: EliminationType
    description: str
    debit_account_code: str
    credit_account_code: str
    amount: Decimal
    entity_a_tenant_id: int | None = None
    entity_b_tenant_id: int | None = None


class EliminationOut(EliminationIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TaxAdjustmentIn(BaseModel):
    period_code: str
    description: str
    amount: Decimal
    category: str = "permanent"
    notes: str | None = None


class TaxAdjustmentOut(TaxAdjustmentIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---- Eliminations ---------------------------------------------------------


@router.get("/eliminations", response_model=list[EliminationOut])
def list_eliminations(period_code: str, db: Session = Depends(get_db)):
    return (
        db.query(EliminationEntry)
        .filter(EliminationEntry.period_code == period_code)
        .order_by(EliminationEntry.id)
        .all()
    )


@router.post(
    "/eliminations",
    response_model=EliminationOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_elimination(payload: EliminationIn, db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    e = EliminationEntry(**payload.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.delete(
    "/eliminations/{eid}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_elimination(eid: int, db: Session = Depends(get_db)):
    e = db.query(EliminationEntry).filter(EliminationEntry.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(e)
    db.commit()
    return {"ok": True}


# ---- Tax adjustments ------------------------------------------------------


@router.get("/tax-adjustments", response_model=list[TaxAdjustmentOut])
def list_tax_adjustments(period_code: str, db: Session = Depends(get_db)):
    return (
        db.query(TaxAdjustment)
        .filter(TaxAdjustment.period_code == period_code)
        .order_by(TaxAdjustment.id)
        .all()
    )


@router.post(
    "/tax-adjustments",
    response_model=TaxAdjustmentOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_tax_adjustment(payload: TaxAdjustmentIn, db: Session = Depends(get_db)):
    if payload.category not in ("permanent", "temporary"):
        raise HTTPException(status_code=400, detail="category must be permanent|temporary")
    t = TaxAdjustment(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ---- Consolidated B/S + P&L ------------------------------------------------


@router.get("/balance-sheet")
def consolidated_balance_sheet(
    as_of: date,
    db: Session = Depends(get_db),
):
    """Consolidated balance sheet: sum across all tenants then strip
    inter-company eliminations.

    Single-tenant deployments still work — eliminations just stay empty.
    """
    def _by_type(acc_type: AccountType, debit_minus_credit: bool) -> dict:
        rows = (
            db.query(
                Account.code,
                Account.name,
                func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
                func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
            )
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(Account.type == acc_type)
            .filter((JournalEntry.entry_date <= as_of) | (JournalEntry.id.is_(None)))
            .group_by(Account.id)
            .all()
        )
        items = []
        total = Decimal("0")
        for r in rows:
            bal = (
                Decimal(r.dr) - Decimal(r.cr) if debit_minus_credit
                else Decimal(r.cr) - Decimal(r.dr)
            )
            if bal == 0:
                continue
            items.append({"code": r.code, "name": r.name, "balance": float(bal)})
            total += bal
        return {"items": items, "total": float(total)}

    assets = _by_type(AccountType.asset, debit_minus_credit=True)
    liabilities = _by_type(AccountType.liability, debit_minus_credit=False)
    equity = _by_type(AccountType.equity, debit_minus_credit=False)

    # Apply eliminations up to the period
    period_prefix = as_of.strftime("%Y")
    elims = (
        db.query(EliminationEntry)
        .filter(EliminationEntry.period_code.startswith(period_prefix))
        .all()
    )
    elim_total = Decimal("0")
    for e in elims:
        elim_total += Decimal(e.amount)
        # The elimination decreases both sides (e.g., intercompany AR ↔ AP)
        for col in (assets["items"], liabilities["items"]):
            for it in col:
                if it["code"] == e.debit_account_code or it["code"] == e.credit_account_code:
                    it["balance"] -= float(e.amount)

    return {
        "as_of": as_of.isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "eliminations_total": float(elim_total),
        "elimination_count": len(elims),
    }


@router.get("/taxable-income")
def taxable_income(
    start: date,
    end: date,
    db: Session = Depends(get_db),
):
    """회계상 순이익 + 가산조정 - 차감조정 = 과세표준."""
    # Book net income for the period
    revenue = (
        db.query(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0))
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(Account.type == AccountType.revenue)
        .filter(JournalEntry.entry_date.between(start, end))
        .scalar()
        or 0
    )
    expense = (
        db.query(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(Account.type == AccountType.expense)
        .filter(JournalEntry.entry_date.between(start, end))
        .scalar()
        or 0
    )
    book_net = Decimal(revenue) - Decimal(expense)

    # Sum adjustments for period codes that fall in [start.year-month, end.year-month]
    period_codes = []
    cur = start.replace(day=1)
    while cur <= end:
        period_codes.append(cur.strftime("%Y-%m"))
        # next month
        y, m = cur.year, cur.month + 1
        if m > 12:
            m, y = 1, y + 1
        cur = cur.replace(year=y, month=m)

    adjustments = (
        db.query(TaxAdjustment)
        .filter(TaxAdjustment.period_code.in_(period_codes))
        .all()
    )
    addition = sum((Decimal(a.amount) for a in adjustments if a.amount > 0), Decimal("0"))
    subtraction = sum((Decimal(-a.amount) for a in adjustments if a.amount < 0), Decimal("0"))
    taxable = book_net + addition - subtraction

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "book_net_income": float(book_net),
        "additions": float(addition),
        "subtractions": float(subtraction),
        "taxable_income": float(taxable),
        "adjustment_count": len(adjustments),
    }
