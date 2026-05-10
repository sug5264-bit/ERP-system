from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ProjectStatus(str, PyEnum):
    active = "active"
    closed = "closed"
    cancelled = "cancelled"


class Project(BaseEntity):
    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("sales_customers.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.active, nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(2000))


class Timesheet(BaseEntity):
    """Hours an employee logged against a project on a date."""

    __tablename__ = "project_timesheets"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("hr_employees.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    description: Mapped[str | None] = mapped_column(String(500))


class ProjectExpense(BaseEntity):
    """Direct expense charged to a project (materials, subcontract, etc.)."""

    __tablename__ = "project_expenses"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), default="material")
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class ProjectRevenue(BaseEntity):
    """Revenue recognized against a project (linked-or-manual entries)."""

    __tablename__ = "project_revenues"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("billing_invoices.id"))
