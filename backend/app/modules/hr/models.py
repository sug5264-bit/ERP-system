from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


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
