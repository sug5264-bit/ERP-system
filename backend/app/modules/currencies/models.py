from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class Currency(BaseEntity):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), default="")
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)


class ExchangeRate(BaseEntity):
    """Rate to convert *one unit* of `currency` into the system base currency."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("currency_id", "as_of_date", name="uq_currency_date"),
    )

    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    rate_to_base: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)

    currency: Mapped[Currency] = relationship()
