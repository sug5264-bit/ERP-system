"""Multi-currency conversion service."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.fx.models import ExchangeRate

BASE_CURRENCY = "KRW"


def get_rate(
    db: Session,
    from_ccy: str,
    to_ccy: str,
    as_of: date | None = None,
) -> Decimal | None:
    """Most recent rate at or before `as_of`. Returns None if not found."""
    if from_ccy == to_ccy:
        return Decimal("1")
    cutoff = as_of or date.today()
    row = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_ccy == from_ccy,
            ExchangeRate.to_ccy == to_ccy,
            ExchangeRate.date <= cutoff,
        )
        .order_by(ExchangeRate.date.desc())
        .first()
    )
    if row is not None:
        return Decimal(row.rate)
    # Try reverse: to_ccy → from_ccy and invert
    rev = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_ccy == to_ccy,
            ExchangeRate.to_ccy == from_ccy,
            ExchangeRate.date <= cutoff,
        )
        .order_by(ExchangeRate.date.desc())
        .first()
    )
    if rev is not None and Decimal(rev.rate) != 0:
        return (Decimal("1") / Decimal(rev.rate)).quantize(Decimal("0.000001"))
    return None


def convert(
    db: Session,
    amount: Decimal,
    from_ccy: str,
    to_ccy: str,
    as_of: date | None = None,
) -> Decimal:
    """Convert; raises ValueError if no rate available."""
    r = get_rate(db, from_ccy, to_ccy, as_of)
    if r is None:
        raise ValueError(f"No rate for {from_ccy}→{to_ccy} on/before {as_of or 'today'}")
    return (Decimal(amount) * r).quantize(Decimal("0.01"))


def realized_fx_diff(
    db: Session,
    *,
    foreign_amount: Decimal,
    foreign_ccy: str,
    booked_at: date,
    settled_at: date,
) -> Decimal:
    """Realized FX gain/loss for a transaction settled later than booked.

    Positive = gain (foreign currency strengthened against base).
    Negative = loss.
    """
    booked_value = convert(db, foreign_amount, foreign_ccy, BASE_CURRENCY, booked_at)
    settled_value = convert(db, foreign_amount, foreign_ccy, BASE_CURRENCY, settled_at)
    return settled_value - booked_value
