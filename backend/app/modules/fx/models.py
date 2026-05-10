from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ExchangeRate(BaseEntity):
    """Daily FX rate snapshot.

    Lookup: SELECT rate WHERE from_ccy=X AND to_ccy=Y AND date<=as_of ORDER BY
    date DESC LIMIT 1 — i.e. most recent rate at-or-before `as_of`.
    """

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("date", "from_ccy", "to_ccy", name="uq_fx_rate_date_pair"),
    )

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    from_ccy: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    to_ccy: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
