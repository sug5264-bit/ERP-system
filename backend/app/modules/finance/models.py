from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class AccountType(str, PyEnum):
    asset = "asset"
    liability = "liability"
    equity = "equity"
    revenue = "revenue"
    expense = "expense"


class Account(BaseEntity):
    __tablename__ = "fin_accounts"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    # Optional display labels per accounting standard. NULL → fall back to `name`.
    ifrs_label: Mapped[str | None] = mapped_column(String(200))
    us_gaap_label: Mapped[str | None] = mapped_column(String(200))


class JournalEntry(BaseEntity):
    __tablename__ = "fin_journal_entries"

    entry_date: Mapped[date] = mapped_column(Date, default=date.today)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class JournalLine(BaseEntity):
    __tablename__ = "fin_journal_lines"

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("fin_journal_entries.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("fin_accounts.id"), nullable=False, index=True
    )
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    memo: Mapped[str | None] = mapped_column(String(255))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class FiscalPeriod(BaseEntity):
    """A bookkeeping period (typically a month). When `is_closed`, journal
    entries dated within [start_date, end_date] are rejected."""

    __tablename__ = "fin_fiscal_periods"
    __table_args__ = (UniqueConstraint("code", name="uq_fiscal_period_code"),)

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
