from datetime import date
from decimal import Decimal
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
    salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
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
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
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
    entitled_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("15"))
    used_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0"))


class Holiday(BaseEntity):
    """Public/company holidays. Excluded from leave business-day calculations.

    `country` is reserved for future multi-region support — for now defaults
    to "KR".
    """

    __tablename__ = "hr_holidays"
    __table_args__ = (UniqueConstraint("date", "country", name="uq_holiday_date_country"),)

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="KR", nullable=False)


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
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bonus: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    allowance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # 4대보험 breakdown (employee share). `deduction` totals these.
    nps: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))      # 국민연금
    nhi: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))      # 건강보험
    ltci: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))     # 장기요양
    ei: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))       # 고용보험
    income_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status: Mapped[PayrollStatus] = mapped_column(
        Enum(PayrollStatus), default=PayrollStatus.draft, nullable=False
    )
    paid_at: Mapped[date | None] = mapped_column(Date)


class Attendance(BaseEntity):
    """One row per (employee, date). Records clock_in/out and computed minutes."""

    __tablename__ = "hr_attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_emp_date"),
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("hr_employees.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    clock_in: Mapped[str | None] = mapped_column(String(8))    # "HH:MM:SS"
    clock_out: Mapped[str | None] = mapped_column(String(8))
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(500))
