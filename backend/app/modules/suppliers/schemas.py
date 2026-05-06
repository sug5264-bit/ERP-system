from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.modules.suppliers.models import POStatus


class SupplierIn(BaseModel):
    code: str
    name: str
    contact_email: EmailStr | None = None
    phone: str | None = None
    business_no: str | None = None
    portal_user_id: int | None = None


class SupplierOut(SupplierIn):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class POItemIn(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal


class POItemOut(POItemIn):
    id: int
    received_qty: Decimal

    class Config:
        from_attributes = True


class POCreate(BaseModel):
    po_no: str
    supplier_id: int
    expected_date: date | None = None
    notes: str | None = None
    items: list[POItemIn] = Field(min_length=1)


class POOut(BaseModel):
    id: int
    po_no: str
    supplier_id: int
    order_date: date
    expected_date: date | None
    status: POStatus
    total: Decimal
    notes: str | None
    items: list[POItemOut]
    supplier: SupplierOut | None = None

    class Config:
        from_attributes = True


class POReceiveLine(BaseModel):
    item_id: int
    quantity: Decimal


class POReceive(BaseModel):
    lines: list[POReceiveLine] = Field(min_length=1)
