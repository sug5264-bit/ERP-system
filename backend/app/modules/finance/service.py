from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.finance.models import (
    Account,
    FiscalPeriod,
    JournalEntry,
    JournalLine,
)
from app.modules.finance.schemas import AccountCreate, JournalEntryCreate


def check_period_open(db: Session, entry_date: date) -> None:
    period = (
        db.query(FiscalPeriod)
        .filter(
            FiscalPeriod.start_date <= entry_date,
            FiscalPeriod.end_date >= entry_date,
            FiscalPeriod.is_closed.is_(True),
        )
        .first()
    )
    if period:
        raise ValueError(
            f"회계기간 {period.code} 마감 상태 — {entry_date} 자 전표 입력 거부"
        )


def list_accounts(db: Session) -> list[Account]:
    return db.query(Account).order_by(Account.code).all()


def create_account(db: Session, payload: AccountCreate) -> Account:
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def list_journal_entries(db: Session) -> list[JournalEntry]:
    return db.query(JournalEntry).order_by(JournalEntry.entry_date.desc()).all()


def create_journal_entry(db: Session, payload: JournalEntryCreate) -> JournalEntry:
    total_debit = sum((line.debit for line in payload.lines), Decimal("0"))
    total_credit = sum((line.credit for line in payload.lines), Decimal("0"))
    if total_debit != total_credit:
        raise ValueError(f"Debits ({total_debit}) must equal credits ({total_credit})")

    entry_date = payload.entry_date or date.today()
    check_period_open(db, entry_date)
    entry = JournalEntry(
        entry_date=entry_date,
        description=payload.description,
        reference=payload.reference,
    )
    for line in payload.lines:
        entry.lines.append(JournalLine(**line.model_dump()))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
