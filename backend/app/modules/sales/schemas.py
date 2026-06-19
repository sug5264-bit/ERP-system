from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.business_no import format_business_no, is_valid_business_no
from app.modules.sales.models import CustomerType, OrderStatus


def _check_biz_no(v: str | None) -> str | None:
    """선택 필드 — 빈 값은 통과, 입력했으면 체크섬 검증 + 정형화."""
    if v is None or v.strip() == "":
        return None
    if not is_valid_business_no(v):
        raise ValueError("유효한 사업자등록번호가 아닙니다 (체크섬 불일치)")
    return format_business_no(v)


class CustomerBase(BaseModel):
    name: str
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    customer_type: CustomerType = CustomerType.business
    external_id: str | None = None
    external_source: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None

    @field_validator("business_no")
    @classmethod
    def _validate_business_no(cls, v: str | None) -> str | None:
        return _check_biz_no(v)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    customer_type: CustomerType | None = None
    external_id: str | None = None
    external_source: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None

    @field_validator("business_no")
    @classmethod
    def _validate_business_no(cls, v: str | None) -> str | None:
        return _check_biz_no(v)


class CustomerOut(CustomerBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SalesOrderUpdate(BaseModel):
    """Editable header fields for an order — line items are immutable.
    Only allowed while the order is still in `draft` status."""
    customer_id: int | None = None
    order_date: date | None = None


class SalesOrderItemIn(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal


class SalesOrderItemOut(SalesOrderItemIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SalesOrderCreate(BaseModel):
    order_no: str
    customer_id: int
    order_date: date | None = None
    items: list[SalesOrderItemIn] = Field(min_length=1)


class SalesOrderOut(BaseModel):
    id: int
    order_no: str
    customer_id: int
    order_date: date
    status: OrderStatus
    total: Decimal
    customer: CustomerOut | None = None
    items: list[SalesOrderItemOut]

    model_config = ConfigDict(from_attributes=True)
