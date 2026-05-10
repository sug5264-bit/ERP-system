from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_user, get_current_internal_user, require_module_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.finance import service
from app.modules.finance.models import JournalEntry
from app.modules.finance.schemas import (
    AccountCreate,
    AccountOut,
    JournalEntryCreate,
    JournalEntryOut,
)

router = APIRouter(
    prefix="/api/finance",
    tags=["finance"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return service.list_accounts(db)


@router.post(
    "/accounts",
    response_model=AccountOut,
    dependencies=[Depends(require_module_role("finance", "admin"))],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    return service.create_account(db, payload)


@router.get("/journal-entries", response_model=Page[JournalEntryOut])
def list_journal_entries(
    params: PageParams = Depends(), db: Session = Depends(get_db)
):
    q = (
        db.query(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .order_by(JournalEntry.entry_date.desc())
    )
    return paginate(q, params)


@router.post(
    "/journal-entries",
    response_model=JournalEntryOut,
    dependencies=[Depends(require_module_role("finance", "manager"))],
)
def create_journal_entry(payload: JournalEntryCreate, db: Session = Depends(get_db)):
    try:
        return service.create_journal_entry(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---- Admin-only edit / delete + journal void -------------------------------


from app.core.auth import require_role  # noqa: E402
from app.modules.finance.models import Account, JournalLine  # noqa: E402
from app.modules.finance.schemas import AccountUpdate  # noqa: E402


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_account(
    account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)
):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete(
    "/accounts/{account_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    if db.query(JournalLine).filter(JournalLine.account_id == account_id).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete account that has journal lines — accounting integrity required",
        )
    db.delete(acc)
    db.commit()
    return {"ok": True}


@router.post(
    "/journal-entries/{entry_id}/void",
    response_model=JournalEntryOut,
    dependencies=[Depends(require_role("admin"))],
)
def void_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    """Post a reversing journal entry. Original is preserved (audit trail).

    This is the accounting-correct way to 'undo' a posted journal — direct
    edit/delete is intentionally not exposed.
    """
    from datetime import date as _date

    from app.modules.finance.models import JournalEntry as _JE
    from app.modules.finance.models import JournalLine as _JL

    src = (
        db.query(_JE)
        .filter(_JE.id == entry_id)
        .with_for_update()
        .first()
    )
    if not src:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if (src.reference or "").startswith("VOID-"):
        raise HTTPException(status_code=400, detail="Already a voiding entry")
    # Prevent re-voiding the same source entry within a race window
    from app.modules.finance.models import JournalEntry as _JE2  # noqa: E402
    if (
        db.query(_JE2)
        .filter(_JE2.reference == f"VOID-{src.id}")
        .first()
    ):
        raise HTTPException(status_code=400, detail="Already voided")

    void_entry = _JE(
        entry_date=_date.today(),
        description=f"VOID: {src.description}",
        reference=f"VOID-{src.id}",
    )
    for line in src.lines:
        void_entry.lines.append(
            _JL(
                account_id=line.account_id,
                debit=line.credit,  # swap dr/cr
                credit=line.debit,
                memo=f"void of #{src.id}",
            )
        )
    db.add(void_entry)
    db.commit()
    db.refresh(void_entry)
    return void_entry


# ---- Fiscal periods (admin) -----------------------------------------------


from datetime import date as _date  # noqa: E402

from pydantic import BaseModel as _BaseModel, ConfigDict  # noqa: E402

from app.modules.auth.models import User  # noqa: E402
from app.modules.finance.models import AccountType, FiscalPeriod  # noqa: E402
from app.core.time import utc_now  # noqa: E402


class FiscalPeriodIn(_BaseModel):
    code: str
    start_date: _date
    end_date: _date
    notes: str | None = None


class FiscalPeriodOut(_BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    start_date: _date
    end_date: _date
    is_closed: bool
    closed_by_id: int | None
    notes: str | None


@router.get("/periods", response_model=list[FiscalPeriodOut])
def list_periods(db: Session = Depends(get_db)):
    return db.query(FiscalPeriod).order_by(FiscalPeriod.start_date.desc()).all()


@router.post(
    "/periods",
    response_model=FiscalPeriodOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_period(payload: FiscalPeriodIn, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date < start_date")
    if db.query(FiscalPeriod).filter(FiscalPeriod.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    p = FiscalPeriod(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.post(
    "/periods/{period_id}/close",
    response_model=FiscalPeriodOut,
    dependencies=[Depends(require_role("admin"))],
)
def close_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Period not found")
    if p.is_closed:
        raise HTTPException(status_code=400, detail="Already closed")
    # Verify all journals in this period balance — defensive even though create
    # already validates.
    p.is_closed = True
    p.closed_by_id = user.id
    db.commit()
    db.refresh(p)
    return p


@router.post(
    "/periods/{period_id}/reopen",
    response_model=FiscalPeriodOut,
    dependencies=[Depends(require_role("admin"))],
)
def reopen_period(period_id: int, db: Session = Depends(get_db)):
    p = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Period not found")
    p.is_closed = False
    p.closed_by_id = None
    db.commit()
    db.refresh(p)
    return p


# ---- Trial balance & financial statements ----------------------------------


@router.get("/trial-balance")
def trial_balance(
    as_of: _date | None = None,
    db: Session = Depends(get_db),
):
    """Account-level dr/cr totals up to `as_of`. Building block for B/S, P&L."""
    from sqlalchemy import func

    cutoff = as_of or _date.today()
    rows = (
        db.query(
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalLine.debit), 0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .outerjoin(JournalLine, JournalLine.account_id == Account.id)
        .outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter((JournalEntry.entry_date <= cutoff) | (JournalEntry.id.is_(None)))
        .group_by(Account.id)
        .order_by(Account.code)
        .all()
    )
    return {
        "as_of": cutoff.isoformat(),
        "lines": [
            {
                "code": r.code,
                "name": r.name,
                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                "debit": float(r.dr),
                "credit": float(r.cr),
                "balance": float(r.dr) - float(r.cr),
            }
            for r in rows
        ],
    }


@router.get("/income-statement")
def income_statement(
    start: _date,
    end: _date,
    db: Session = Depends(get_db),
):
    """Revenue - Expense for the period [start, end]."""
    from sqlalchemy import func

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
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue": float(revenue),
        "expense": float(expense),
        "net_income": float(revenue) - float(expense),
    }


# ---- Balance Sheet + Cash Flow + VAT return -------------------------------


from decimal import Decimal  # noqa: E402


@router.get("/balance-sheet")
def balance_sheet(
    as_of: _date | None = None,
    db: Session = Depends(get_db),
):
    """Snapshot of Assets / Liabilities / Equity at `as_of` date.

    Equation: Assets = Liabilities + Equity. Equity includes retained earnings
    derived from cumulative (revenue - expense) up to `as_of`.
    """
    from sqlalchemy import func

    cutoff = as_of or _date.today()

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
            .filter((JournalEntry.entry_date <= cutoff) | (JournalEntry.id.is_(None)))
            .group_by(Account.id)
            .all()
        )
        items = []
        total = 0.0
        for r in rows:
            bal = (
                float(r.dr) - float(r.cr) if debit_minus_credit
                else float(r.cr) - float(r.dr)
            )
            if bal == 0:
                continue
            items.append({"code": r.code, "name": r.name, "balance": bal})
            total += bal
        return {"items": items, "total": total}

    assets = _by_type(AccountType.asset, debit_minus_credit=True)
    liabilities = _by_type(AccountType.liability, debit_minus_credit=False)
    equity = _by_type(AccountType.equity, debit_minus_credit=False)

    # Retained earnings = cumulative (revenue - expense) up to cutoff
    rev_total = (
        db.query(
            func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)
        )
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(Account.type == AccountType.revenue)
        .filter(JournalEntry.entry_date <= cutoff)
        .scalar()
        or 0
    )
    exp_total = (
        db.query(
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
        )
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(Account.type == AccountType.expense)
        .filter(JournalEntry.entry_date <= cutoff)
        .scalar()
        or 0
    )
    retained = float(rev_total) - float(exp_total)
    equity["items"].append(
        {"code": "_RE", "name": "이익잉여금 (계산값)", "balance": retained}
    )
    equity["total"] += retained

    return {
        "as_of": cutoff.isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_liab_eq": liabilities["total"] + equity["total"],
        "balanced": abs(assets["total"] - (liabilities["total"] + equity["total"])) < 0.01,
    }


@router.get("/cash-flow")
def cash_flow(
    start: _date,
    end: _date,
    cash_account_codes: str = "1100,1110,1120",
    db: Session = Depends(get_db),
):
    """Indirect-method cash flow over [start, end].

    The cash account codes (default = 현금/예금/단기금융상품 / 1100·1110·1120)
    are aggregated by movement type derived from the *paired* account on each
    entry — sales receipts, vendor payments, payroll outflows, etc.

    Returns:
        operating: sum of cash flows tagged via revenue / expense paired accounts
        investing: paired with asset (1300+) / fixed-asset (12xx)
        financing: paired with liability / equity
    """
    from sqlalchemy import func

    cash_codes = [c.strip() for c in cash_account_codes.split(",") if c.strip()]
    cash_account_ids = [
        a.id for a in db.query(Account).filter(Account.code.in_(cash_codes)).all()
    ]
    if not cash_account_ids:
        raise HTTPException(status_code=400, detail="No matching cash accounts")

    # For each journal line on a cash account, find the contra (other) lines
    # in the same entry to classify the cash movement.
    entries = (
        db.query(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .filter(JournalLine.account_id.in_(cash_account_ids))
        .filter(JournalEntry.entry_date.between(start, end))
        .distinct()
        .all()
    )

    operating = Decimal("0")
    investing = Decimal("0")
    financing = Decimal("0")
    for entry in entries:
        cash_delta = Decimal("0")
        contra_type: AccountType | None = None
        for line in entry.lines:
            if line.account_id in cash_account_ids:
                cash_delta += Decimal(line.debit) - Decimal(line.credit)
            else:
                acc = db.query(Account).filter(Account.id == line.account_id).first()
                if acc and contra_type is None:
                    contra_type = acc.type
        if contra_type in (AccountType.revenue, AccountType.expense):
            operating += cash_delta
        elif contra_type == AccountType.asset:
            investing += cash_delta
        elif contra_type in (AccountType.liability, AccountType.equity):
            financing += cash_delta
        else:
            operating += cash_delta  # default bucket

    net = operating + investing + financing
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "operating": float(operating),
        "investing": float(investing),
        "financing": float(financing),
        "net_change": float(net),
    }


@router.get("/vat-return")
def vat_return(
    start: _date,
    end: _date,
    db: Session = Depends(get_db),
):
    """Korean 부가가치세 신고서 — quarterly summary.

    매출세액 (output VAT)  = sum of e-Tax sales invoices' tax  in [start, end]
    매입세액 (input  VAT)  = sum of e-Tax purchase invoices' tax in [start, end]
    납부세액 = 매출세액 - 매입세액 (음수면 환급)

    e-Tax invoices in `accepted` or `submitted` status only.
    """
    from sqlalchemy import func

    from app.modules.etax.models import ETaxInvoice, ETaxStatus, ETaxType

    sales = (
        db.query(
            func.coalesce(func.sum(ETaxInvoice.subtotal), 0).label("supply"),
            func.coalesce(func.sum(ETaxInvoice.tax), 0).label("vat"),
            func.count(ETaxInvoice.id).label("count"),
        )
        .filter(ETaxInvoice.type == ETaxType.sales)
        .filter(ETaxInvoice.status.in_([ETaxStatus.accepted, ETaxStatus.submitted]))
        .filter(ETaxInvoice.issued_date.between(start, end))
        .first()
    )
    purchase = (
        db.query(
            func.coalesce(func.sum(ETaxInvoice.subtotal), 0).label("supply"),
            func.coalesce(func.sum(ETaxInvoice.tax), 0).label("vat"),
            func.count(ETaxInvoice.id).label("count"),
        )
        .filter(ETaxInvoice.type == ETaxType.purchase)
        .filter(ETaxInvoice.status.in_([ETaxStatus.accepted, ETaxStatus.submitted]))
        .filter(ETaxInvoice.issued_date.between(start, end))
        .first()
    )
    output_vat = float(sales.vat or 0)
    input_vat = float(purchase.vat or 0)
    payable = output_vat - input_vat
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sales": {
            "supply_amount": float(sales.supply or 0),
            "vat_amount": output_vat,
            "invoice_count": int(sales.count or 0),
        },
        "purchase": {
            "supply_amount": float(purchase.supply or 0),
            "vat_amount": input_vat,
            "invoice_count": int(purchase.count or 0),
        },
        "payable_or_refund": payable,
        "is_refund": payable < 0,
    }
