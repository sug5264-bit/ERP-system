from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.finance.models import Account, JournalEntry, JournalLine
from app.modules.finance.schemas import AccountCreate, JournalEntryCreate


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

    entry = JournalEntry(
        entry_date=payload.entry_date or date.today(),
        description=payload.description,
        reference=payload.reference,
    )
    for line in payload.lines:
        entry.lines.append(JournalLine(**line.model_dump()))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
