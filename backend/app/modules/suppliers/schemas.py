from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.modules.suppliers.models import POStatus


class SupplierIn(BaseModel):
    code: str
    name: str
    contact_email: EmailStr | None = None
    phone: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    portal_user_id: int | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_email: EmailStr | None = None
    phone: str | None = None
    business_no: str | None = None
    representative: str | None = None
    address: str | None = None
    business_type: str | None = None
    business_item: str | None = None
    fax: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    is_active: bool | None = None


class CreateSupplierWithPortalUser(BaseModel):
    """Create a Supplier together with a fresh portal-user account."""
    code: str
    name: str
    contact_email: EmailStr
    phone: str | None = None
    business_no: str | None = None
    portal_full_name: str
    portal_password: str = Field(min_length=8)


class SupplierOut(SupplierIn):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class POItemIn(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal


class POItemOut(POItemIn):
    id: int
    received_qty: Decimal

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class POReceiveLine(BaseModel):
    item_id: int
    quantity: Decimal


class POReceive(BaseModel):
    lines: list[POReceiveLine] = Field(min_length=1)
