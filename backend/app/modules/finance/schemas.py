from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.modules.finance.models import AccountType


class AccountBase(BaseModel):
    code: str
    name: str
    type: AccountType


class AccountCreate(AccountBase):
    pass


class AccountOut(AccountBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class JournalLineIn(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    memo: str | None = None


class JournalLineOut(JournalLineIn):
    id: int
    account: AccountOut | None = None

    model_config = ConfigDict(from_attributes=True)


class JournalEntryCreate(BaseModel):
    entry_date: date | None = None
    description: str
    reference: str | None = None
    lines: list[JournalLineIn] = Field(min_length=2)


class JournalEntryOut(BaseModel):
    id: int
    entry_date: date
    description: str
    reference: str | None = None
    lines: list[JournalLineOut]

    model_config = ConfigDict(from_attributes=True)
