from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.currencies.models import Currency, ExchangeRate


def get_base_currency(db: Session) -> Currency | None:
    return db.query(Currency).filter(Currency.is_base.is_(True)).first()


def get_currency(db: Session, code: str) -> Currency | None:
    return db.query(Currency).filter(Currency.code == code.upper()).first()


def latest_rate(db: Session, currency_id: int) -> ExchangeRate | None:
    return (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency_id == currency_id)
        .order_by(ExchangeRate.as_of_date.desc())
        .first()
    )


def convert(
    db: Session, amount: Decimal, from_code: str, to_code: str
) -> tuple[Decimal, Decimal, date]:
    """Returns (converted_amount, rate_used, rate_date)."""
    base = get_base_currency(db)
    if not base:
        raise ValueError("No base currency configured")

    src = get_currency(db, from_code)
    dst = get_currency(db, to_code)
    if not src or not dst:
        raise ValueError("Unknown currency")

    if src.id == dst.id:
        return amount, Decimal("1"), date.today()

    src_rate = Decimal("1") if src.is_base else _require_rate(db, src.id)
    dst_rate = Decimal("1") if dst.is_base else _require_rate(db, dst.id)

    # amount * (src→base) / (dst→base) = amount in destination
    base_amount = Decimal(amount) * Decimal(src_rate)
    converted = base_amount / Decimal(dst_rate)

    rate_used = Decimal(src_rate) / Decimal(dst_rate)
    rate_date = latest_rate(db, src.id).as_of_date if not src.is_base else (
        latest_rate(db, dst.id).as_of_date if not dst.is_base else date.today()
    )
    return converted, rate_used, rate_date


def _require_rate(db: Session, currency_id: int) -> Decimal:
    rate = latest_rate(db, currency_id)
    if not rate:
        raise ValueError("No exchange rate available for currency")
    return Decimal(rate.rate_to_base)
