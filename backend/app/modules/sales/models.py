from datetime import date
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class OrderStatus(str, PyEnum):
    draft = "draft"
    confirmed = "confirmed"
    shipped = "shipped"
    cancelled = "cancelled"


class Customer(BaseEntity):
    """거래처 (매출처). 한국식 세금계산서/거래명세표 발행에 필요한
    사업자등록증 항목을 모두 보유."""

    __tablename__ = "sales_customers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    company: Mapped[str | None] = mapped_column(String(200))
    # 사업자등록증 항목 (세금계산서/거래명세표 필수)
    business_no: Mapped[str | None] = mapped_column(String(20), index=True)
    representative: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(500))
    business_type: Mapped[str | None] = mapped_column(String(100))  # 업태
    business_item: Mapped[str | None] = mapped_column(String(200))  # 종목
    fax: Mapped[str | None] = mapped_column(String(50))
    contact_person: Mapped[str | None] = mapped_column(String(100))  # 담당자
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account: Mapped[str | None] = mapped_column(String(100))

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True)


class SalesOrder(BaseEntity):
    __tablename__ = "sales_orders"

    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("sales_customers.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.draft)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True)

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["SalesOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class SalesOrderItem(BaseEntity):
    __tablename__ = "sales_order_items"

    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[SalesOrder] = relationship(back_populates="items")
