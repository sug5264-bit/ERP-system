from datetime import date

from sqlalchemy.orm import Session

from app.modules.hr.models import Department, Employee
from app.modules.hr.schemas import DepartmentCreate, EmployeeCreate, EmployeeUpdate


def list_departments(db: Session) -> list[Department]:
    return db.query(Department).order_by(Department.name).all()


def create_department(db: Session, payload: DepartmentCreate) -> Department:
    dept = Department(**payload.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def list_employees(db: Session) -> list[Employee]:
    return db.query(Employee).order_by(Employee.employee_no).all()


def get_employee(db: Session, employee_id: int) -> Employee | None:
    return db.query(Employee).filter(Employee.id == employee_id).first()


def create_employee(db: Session, payload: EmployeeCreate) -> Employee:
    data = payload.model_dump()
    if data.get("hire_date") is None:
        data["hire_date"] = date.today()
    emp = Employee(**data)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def update_employee(db: Session, employee_id: int, payload: EmployeeUpdate) -> Employee | None:
    emp = get_employee(db, employee_id)
    if not emp:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    db.commit()
    db.refresh(emp)
    return emp


def delete_employee(db: Session, employee_id: int) -> bool:
    emp = get_employee(db, employee_id)
    if not emp:
        return False
    db.delete(emp)
    db.commit()
    return True
