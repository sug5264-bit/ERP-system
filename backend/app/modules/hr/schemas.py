from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class DepartmentBase(BaseModel):
    name: str
    description: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentOut(DepartmentBase):
    id: int

    class Config:
        from_attributes = True


class EmployeeBase(BaseModel):
    employee_no: str
    full_name: str
    email: EmailStr
    position: str | None = None
    hire_date: date | None = None
    salary: Decimal = Decimal("0")
    department_id: int | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    salary: Decimal | None = None
    department_id: int | None = None


class EmployeeOut(EmployeeBase):
    id: int
    department: DepartmentOut | None = None

    class Config:
        from_attributes = True
