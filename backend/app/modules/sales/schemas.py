from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.modules.sales.models import OrderStatus


class CustomerBase(BaseModel):
    name: str
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None


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
