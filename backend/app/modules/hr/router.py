from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_user, require_module_role
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.modules.hr import service
from app.modules.hr.models import Employee
from app.modules.hr.schemas import (
    DepartmentCreate,
    DepartmentOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
)

router = APIRouter(
    prefix="/api/hr",
    tags=["hr"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return service.list_departments(db)


@router.post(
    "/departments",
    response_model=DepartmentOut,
    dependencies=[Depends(require_module_role("hr", "admin"))],
)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    return service.create_department(db, payload)


@router.get("/employees", response_model=Page[EmployeeOut])
def list_employees(params: PageParams = Depends(), db: Session = Depends(get_db)):
    q = (
        db.query(Employee)
        .options(selectinload(Employee.department))
        .order_by(Employee.employee_no)
    )
    return paginate(q, params)


@router.get("/employees/export")
def export_employees(format: str = Query("csv"), db: Session = Depends(get_db)):
    employees = service.list_employees(db)
    headers = ["사번", "이름", "이메일", "직책", "부서", "급여", "입사일"]
    rows = [
        [
            e.employee_no,
            e.full_name,
            e.email,
            e.position or "",
            e.department.name if e.department else "",
            float(e.salary),
            e.hire_date.isoformat() if e.hire_date else "",
        ]
        for e in employees
    ]
    return export_table(rows, headers, "employees", format)


@router.post(
    "/employees",
    response_model=EmployeeOut,
    dependencies=[Depends(require_module_role("hr", "manager"))],
)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    return service.create_employee(db, payload)


@router.patch(
    "/employees/{employee_id}",
    response_model=EmployeeOut,
    dependencies=[Depends(require_module_role("hr", "manager"))],
)
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = service.update_employee(db, employee_id, payload)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.delete(
    "/employees/{employee_id}",
    dependencies=[Depends(require_module_role("hr", "admin"))],
)
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    if not service.delete_employee(db, employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"ok": True}
