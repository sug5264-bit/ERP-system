from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class CurrencyBase(BaseModel):
    code: str
    name: str
    symbol: str = ""
    is_base: bool = False


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyOut(CurrencyBase):
    id: int

    class Config:
        from_attributes = True


class ExchangeRateIn(BaseModel):
    rate_to_base: Decimal
    as_of_date: date | None = None


class ExchangeRateOut(BaseModel):
    id: int
    currency_id: int
    rate_to_base: Decimal
    as_of_date: date

    class Config:
        from_attributes = True


class ConvertResult(BaseModel):
    amount: Decimal
    from_currency: str
    to_currency: str
    converted: Decimal
    rate_used: Decimal
    as_of_date: date
