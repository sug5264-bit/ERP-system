from datetime import date
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class LeaveType(str, PyEnum):
    annual = "annual"
    sick = "sick"
    personal = "personal"
    maternity = "maternity"
    other = "other"


class LeaveStatus(str, PyEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class PayrollStatus(str, PyEnum):
    draft = "draft"
    issued = "issued"
    paid = "paid"


class Department(BaseEntity):
    __tablename__ = "hr_departments"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class Employee(BaseEntity):
    __tablename__ = "hr_employees"

    employee_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    position: Mapped[str | None] = mapped_column(String(100))
    hire_date: Mapped[date] = mapped_column(Date, default=date.today)
    salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("hr_departments.id"))

    department: Mapped[Department | None] = relationship(back_populates="employees")


class LeaveRequest(BaseEntity):
    __tablename__ = "hr_leave_requests"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("hr_employees.id"), nullable=False, index=True
    )
    type: Mapped[LeaveType] = mapped_column(Enum(LeaveType), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus), default=LeaveStatus.pending, nullable=False, index=True
    )
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_comment: Mapped[str | None] = mapped_column(String(500))


class LeaveBalance(BaseEntity):
    """Annual entitlement + remaining days per employee per year."""

    __tablename__ = "hr_leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", "type", name="uq_leave_balance"),
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("hr_employees.id"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[LeaveType] = mapped_column(Enum(LeaveType), nullable=False)
    entitled_days: Mapped[float] = mapped_column(Numeric(5, 1), default=15)
    used_days: Mapped[float] = mapped_column(Numeric(5, 1), default=0)


class Payroll(BaseEntity):
    """A monthly payroll for one employee (period code = YYYY-MM)."""

    __tablename__ = "hr_payrolls"
    __table_args__ = (
        UniqueConstraint("employee_id", "period_code", name="uq_payroll_per_employee_period"),
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("hr_employees.id"), nullable=False, index=True
    )
    period_code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-05"
    base_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    bonus: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    allowance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    deduction: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # 4대보험 등
    income_tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    net_pay: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[PayrollStatus] = mapped_column(
        Enum(PayrollStatus), default=PayrollStatus.draft, nullable=False
    )
    paid_at: Mapped[date | None] = mapped_column(Date)
