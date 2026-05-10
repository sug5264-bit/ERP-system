"""Auto-posting helpers — convert business events into GL journal entries.

Standard mapping (Korean GAAP simplified):
    issue_invoice    Dr AR             total
                       Cr Revenue       subtotal
                       Cr VAT_payable   tax
    record_payment   Dr Cash           amount
                       Cr AR            amount
    confirm_order    Dr COGS           cost
                       Cr Inventory     cost   (relieved at avg_cost)

Account lookup is by **Account.code**. The convention is:
    1100 = Cash / Bank
    1200 = Accounts Receivable
    1300 = Inventory asset
    2150 = VAT payable
    4100 = Sales revenue
    5100 = COGS

If a code is missing the post is skipped and a warning is logged — auto-post
is best-effort and never blocks the originating business action.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.finance.models import Account, JournalEntry, JournalLine

log = logging.getLogger("erp.finance.autopost")


# Default Account.code mapping. Override by changing the Account record's
# code in the DB — no env var needed.
ACCOUNT_CODES = {
    "cash": "1100",
    "ar": "1200",
    "inventory": "1300",
    "vat_payable": "2150",
    "revenue": "4100",
    "cogs": "5100",
}


def _account(db: Session, key: str) -> Account | None:
    code = ACCOUNT_CODES.get(key)
    if not code:
        return None
    return db.query(Account).filter(Account.code == code).first()


def _post(
    db: Session,
    *,
    description: str,
    reference: str,
    lines: list[tuple[Account, Decimal, Decimal]],
    entry_date: date | None = None,
) -> JournalEntry | None:
    """Create a balanced JournalEntry. Caller must pass (account, debit, credit)
    triples. Skips silently if any account is missing — partial posting is
    worse than no posting."""
    if any(acc is None for acc, _, _ in lines):
        log.warning("auto-post skipped (%s): missing account in mapping", reference)
        return None
    total_debit = sum((d for _, d, _ in lines), Decimal("0"))
    total_credit = sum((c for _, _, c in lines), Decimal("0"))
    if total_debit != total_credit:
        log.error(
            "auto-post unbalanced (%s): debits %s != credits %s",
            reference,
            total_debit,
            total_credit,
        )
        return None
    entry = JournalEntry(
        entry_date=entry_date or date.today(),
        description=description,
        reference=reference,
    )
    for acc, debit, credit in lines:
        entry.lines.append(
            JournalLine(account_id=acc.id, debit=debit, credit=credit, memo=description)
        )
    db.add(entry)
    db.flush()  # caller commits
    return entry


def post_invoice_issued(db: Session, invoice) -> JournalEntry | None:
    ar = _account(db, "ar")
    rev = _account(db, "revenue")
    vat = _account(db, "vat_payable")
    return _post(
        db,
        description=f"Invoice {invoice.invoice_no} 발행",
        reference=f"INV-{invoice.invoice_no}",
        lines=[
            (ar, Decimal(invoice.total), Decimal("0")),
            (rev, Decimal("0"), Decimal(invoice.subtotal)),
            (vat, Decimal("0"), Decimal(invoice.tax)),
        ],
        entry_date=invoice.issued_date,
    )


def post_payment_received(db: Session, payment) -> JournalEntry | None:
    cash = _account(db, "cash")
    ar = _account(db, "ar")
    return _post(
        db,
        description=f"Payment for invoice #{payment.invoice_id}",
        reference=f"PAY-{payment.id}",
        lines=[
            (cash, Decimal(payment.amount), Decimal("0")),
            (ar, Decimal("0"), Decimal(payment.amount)),
        ],
        entry_date=payment.paid_at,
    )


def post_cogs(db: Session, *, order_no: str, cost: Decimal) -> JournalEntry | None:
    if cost <= 0:
        return None
    cogs = _account(db, "cogs")
    inv = _account(db, "inventory")
    return _post(
        db,
        description=f"COGS for order {order_no}",
        reference=f"COGS-{order_no}",
        lines=[
            (cogs, cost, Decimal("0")),
            (inv, Decimal("0"), cost),
        ],
    )
