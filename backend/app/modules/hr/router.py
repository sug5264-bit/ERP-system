from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_user, get_current_internal_user, require_module_role
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
    dependencies=[Depends(get_current_internal_user)],
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
def export_employees(format: str = Query("csv"), inline: bool = Query(False), db: Session = Depends(get_db)):
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
    return export_table(rows, headers, "employees", format, inline=inline)


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


# ---- Admin-only department edit / delete -----------------------------------


from app.core.auth import require_role  # noqa: E402
from app.modules.hr.models import Department  # noqa: E402
from app.modules.hr.schemas import DepartmentUpdate  # noqa: E402


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_department(
    department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db)
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(dept, k, v)
    db.commit()
    db.refresh(dept)
    return dept


@router.delete(
    "/departments/{department_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_department(department_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if dept.employees:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete department with assigned employees",
        )
    db.delete(dept)
    db.commit()
    return {"ok": True}


# ---- Leave + Payroll ------------------------------------------------------


from datetime import date as _date  # noqa: E402
from decimal import Decimal as _D  # noqa: E402

from pydantic import BaseModel as _BaseModel, ConfigDict as _Cfg  # noqa: E402

from app.modules.auth.models import User as _User  # noqa: E402
from app.modules.hr.models import (  # noqa: E402
    LeaveBalance,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    Payroll,
    PayrollStatus,
)


class LeaveRequestIn(_BaseModel):
    employee_id: int
    type: LeaveType
    start_date: _date
    end_date: _date
    reason: str | None = None


class LeaveRequestOut(_BaseModel):
    id: int
    employee_id: int
    type: LeaveType
    start_date: _date
    end_date: _date
    days: _D
    reason: str | None
    status: LeaveStatus
    decided_by_id: int | None
    decided_comment: str | None
    model_config = _Cfg(from_attributes=True)


class LeaveDecisionIn(_BaseModel):
    comment: str | None = None


def _business_days(start: _date, end: _date) -> int:
    if end < start:
        return 0
    days = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days += 1
        cur = _date.fromordinal(cur.toordinal() + 1)
    return days


@router.get("/leave-requests", response_model=list[LeaveRequestOut])
def list_leave_requests(
    status: LeaveStatus | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(LeaveRequest)
    if status:
        q = q.filter(LeaveRequest.status == status)
    if employee_id is not None:
        q = q.filter(LeaveRequest.employee_id == employee_id)
    return q.order_by(LeaveRequest.start_date.desc()).all()


@router.post("/leave-requests", response_model=LeaveRequestOut)
def submit_leave_request(payload: LeaveRequestIn, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date < start_date")
    days = _business_days(payload.start_date, payload.end_date)
    if days <= 0:
        raise HTTPException(status_code=400, detail="No business days in range")
    req = LeaveRequest(
        employee_id=payload.employee_id,
        type=payload.type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        days=days,
        reason=payload.reason,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/leave-requests/{req_id}/approve",
    response_model=LeaveRequestOut,
    dependencies=[Depends(require_role("manager"))],
)
def approve_leave(
    req_id: int,
    payload: LeaveDecisionIn,
    db: Session = Depends(get_db),
    user: _User = Depends(get_current_user),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).with_for_update().first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    if req.status != LeaveStatus.pending:
        raise HTTPException(status_code=400, detail=f"Already {req.status.value}")

    # Decrement balance (creating a row if needed). Lock so concurrent
    # approvals for the same employee+year+type serialize on used_days.
    bal = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == req.employee_id,
            LeaveBalance.year == req.start_date.year,
            LeaveBalance.type == req.type,
        )
        .with_for_update()
        .first()
    )
    if not bal:
        bal = LeaveBalance(
            employee_id=req.employee_id,
            year=req.start_date.year,
            type=req.type,
            entitled_days=15,
        )
        db.add(bal)
        db.flush()
    new_used = _D(bal.used_days) + _D(req.days)
    if new_used > _D(bal.entitled_days):
        raise HTTPException(
            status_code=400,
            detail=f"잔여 휴가 부족: 사용 {bal.used_days}+{req.days} > 한도 {bal.entitled_days}",
        )
    bal.used_days = new_used
    req.status = LeaveStatus.approved
    req.decided_by_id = user.id
    req.decided_comment = payload.comment
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/leave-requests/{req_id}/reject",
    response_model=LeaveRequestOut,
    dependencies=[Depends(require_role("manager"))],
)
def reject_leave(
    req_id: int,
    payload: LeaveDecisionIn,
    db: Session = Depends(get_db),
    user: _User = Depends(get_current_user),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    if req.status != LeaveStatus.pending:
        raise HTTPException(status_code=400, detail=f"Already {req.status.value}")
    req.status = LeaveStatus.rejected
    req.decided_by_id = user.id
    req.decided_comment = payload.comment
    db.commit()
    db.refresh(req)
    return req


# Payroll -------------------------------------------------------------------


class PayrollIn(_BaseModel):
    employee_id: int
    period_code: str  # "2026-05"
    base_salary: _D | None = None  # defaults to employee.salary / 12
    bonus: _D = _D("0")
    allowance: _D = _D("0")
    deduction: _D = _D("0")
    income_tax: _D | None = None  # auto-calc if None


class PayrollOut(_BaseModel):
    id: int
    employee_id: int
    period_code: str
    base_salary: _D
    bonus: _D
    allowance: _D
    deduction: _D
    income_tax: _D
    net_pay: _D
    status: PayrollStatus
    paid_at: _date | None
    model_config = _Cfg(from_attributes=True)


def _korean_income_tax(taxable: _D) -> _D:
    """Very rough simplified bracket — replace with NTS table in production."""
    if taxable <= _D("1500000"):
        return (taxable * _D("0.06")).quantize(_D("1"))
    if taxable <= _D("4500000"):
        return (taxable * _D("0.15") - _D("90000")).quantize(_D("1"))
    if taxable <= _D("8800000"):
        return (taxable * _D("0.24") - _D("522000")).quantize(_D("1"))
    return (taxable * _D("0.35") - _D("1490000")).quantize(_D("1"))


@router.get("/payrolls", response_model=list[PayrollOut])
def list_payrolls(
    period_code: str | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Payroll)
    if period_code:
        q = q.filter(Payroll.period_code == period_code)
    if employee_id is not None:
        q = q.filter(Payroll.employee_id == employee_id)
    return q.order_by(Payroll.period_code.desc(), Payroll.employee_id).all()


@router.post(
    "/payrolls",
    response_model=PayrollOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_payroll(payload: PayrollIn, db: Session = Depends(get_db)):
    if (
        db.query(Payroll)
        .filter(
            Payroll.employee_id == payload.employee_id,
            Payroll.period_code == payload.period_code,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Payroll already exists for this period")
    emp = (
        db.query(Employee).filter(Employee.id == payload.employee_id).first()
        if payload.base_salary is None
        else None
    )
    if payload.base_salary is None and not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    base = payload.base_salary if payload.base_salary is not None else _D(emp.salary) / 12
    base = _D(base).quantize(_D("1"))
    gross = base + _D(payload.bonus) + _D(payload.allowance)
    income_tax = (
        payload.income_tax
        if payload.income_tax is not None
        else _korean_income_tax(gross - _D(payload.deduction))
    )
    net = gross - _D(payload.deduction) - _D(income_tax)

    p = Payroll(
        employee_id=payload.employee_id,
        period_code=payload.period_code,
        base_salary=base,
        bonus=payload.bonus,
        allowance=payload.allowance,
        deduction=payload.deduction,
        income_tax=income_tax,
        net_pay=net,
        status=PayrollStatus.draft,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.post(
    "/payrolls/{pid}/issue",
    response_model=PayrollOut,
    dependencies=[Depends(require_role("admin"))],
)
def issue_payroll(pid: int, db: Session = Depends(get_db)):
    p = (
        db.query(Payroll)
        .filter(Payroll.id == pid)
        .with_for_update()
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p.status != PayrollStatus.draft:
        raise HTTPException(status_code=400, detail="Only draft can be issued")
    p.status = PayrollStatus.issued
    db.commit()
    db.refresh(p)
    return p


@router.post(
    "/payrolls/{pid}/mark-paid",
    response_model=PayrollOut,
    dependencies=[Depends(require_role("admin"))],
)
def mark_paid(pid: int, db: Session = Depends(get_db)):
    p = (
        db.query(Payroll)
        .filter(Payroll.id == pid)
        .with_for_update()
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p.status == PayrollStatus.paid:
        return p
    if p.status != PayrollStatus.issued:
        raise HTTPException(status_code=400, detail="Only issued payroll can be marked paid")
    p.status = PayrollStatus.paid
    p.paid_at = _date.today()
    db.commit()
    db.refresh(p)
    return p
