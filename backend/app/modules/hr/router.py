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


def _business_days(start: _date, end: _date, db: Session | None = None) -> int:
    """Count weekdays in [start, end] excluding Saturdays, Sundays, and any
    Korean public holiday rows registered in `hr_holidays`."""
    if end < start:
        return 0
    holiday_dates: set[_date] = set()
    if db is not None:
        from app.modules.hr.models import Holiday  # noqa: E402

        rows = (
            db.query(Holiday.date)
            .filter(Holiday.date >= start, Holiday.date <= end)
            .all()
        )
        holiday_dates = {r[0] for r in rows}
    days = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holiday_dates:
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


@router.post(
    "/leave-requests",
    response_model=LeaveRequestOut,
    dependencies=[Depends(require_module_role("hr", "staff"))],
)
def submit_leave_request(payload: LeaveRequestIn, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date < start_date")
    days = _business_days(payload.start_date, payload.end_date, db=db)
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
    nps: _D
    nhi: _D
    ltci: _D
    ei: _D
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

    # Auto-compute 4대보험 (employee share) and add to deduction
    from app.modules.hr.insurance import calculate_4_insurances

    ins = calculate_4_insurances(gross)
    deduction = _D(payload.deduction) + ins["total"]

    income_tax = (
        payload.income_tax
        if payload.income_tax is not None
        else _korean_income_tax(gross - deduction)
    )
    net = gross - deduction - _D(income_tax)

    p = Payroll(
        employee_id=payload.employee_id,
        period_code=payload.period_code,
        base_salary=base,
        bonus=payload.bonus,
        allowance=payload.allowance,
        deduction=deduction,
        nps=ins["nps"],
        nhi=ins["nhi"],
        ltci=ins["ltci"],
        ei=ins["ei"],
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


# ---- Holidays --------------------------------------------------------------


from app.modules.hr.models import Holiday  # noqa: E402


class HolidayIn(_BaseModel):
    date: _date
    name: str
    country: str = "KR"


class HolidayOut(_BaseModel):
    id: int
    date: _date
    name: str
    country: str
    model_config = _Cfg(from_attributes=True)


@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(
    year: int | None = None,
    country: str = "KR",
    db: Session = Depends(get_db),
):
    q = db.query(Holiday).filter(Holiday.country == country)
    if year is not None:
        from datetime import date as _D

        q = q.filter(Holiday.date >= _D(year, 1, 1), Holiday.date <= _D(year, 12, 31))
    return q.order_by(Holiday.date).all()


@router.post(
    "/holidays",
    response_model=HolidayOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_holiday(payload: HolidayIn, db: Session = Depends(get_db)):
    if (
        db.query(Holiday)
        .filter(Holiday.date == payload.date, Holiday.country == payload.country)
        .first()
    ):
        raise HTTPException(status_code=400, detail="Already exists")
    h = Holiday(**payload.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.delete(
    "/holidays/{hid}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_holiday(hid: int, db: Session = Depends(get_db)):
    h = db.query(Holiday).filter(Holiday.id == hid).first()
    if not h:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(h)
    db.commit()
    return {"ok": True}


@router.post(
    "/holidays/seed-korea",
    dependencies=[Depends(require_role("admin"))],
)
def seed_korea_holidays(year: int, db: Session = Depends(get_db)):
    """Insert the recurring Korean public holidays for the given year. Lunar
    holidays (Seollal/Chuseok) need to be entered manually each year — only
    the fixed-date set is auto-seeded here."""
    from datetime import date as _D

    fixed = [
        (_D(year, 1, 1), "신정"),
        (_D(year, 3, 1), "삼일절"),
        (_D(year, 5, 5), "어린이날"),
        (_D(year, 6, 6), "현충일"),
        (_D(year, 8, 15), "광복절"),
        (_D(year, 10, 3), "개천절"),
        (_D(year, 10, 9), "한글날"),
        (_D(year, 12, 25), "성탄절"),
    ]
    inserted = 0
    for d, name in fixed:
        if (
            db.query(Holiday)
            .filter(Holiday.date == d, Holiday.country == "KR")
            .first()
        ):
            continue
        db.add(Holiday(date=d, name=name, country="KR"))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "year": year}


# ---- Attendance -----------------------------------------------------------


from datetime import datetime as _dt  # noqa: E402

from app.modules.hr.models import Attendance  # noqa: E402


def _hms_to_min(s: str | None) -> int | None:
    if not s:
        return None
    try:
        parts = s.split(":")
        h, m = int(parts[0]), int(parts[1])
        return h * 60 + m
    except (ValueError, IndexError):
        return None


class AttendanceClockIn(_BaseModel):
    employee_id: int
    date: _date | None = None
    time: str | None = None  # "HH:MM" or HH:MM:SS; default = now


class AttendanceClockOut(_BaseModel):
    employee_id: int
    date: _date | None = None
    time: str | None = None
    note: str | None = None


class AttendanceOut(_BaseModel):
    id: int
    employee_id: int
    date: _date
    clock_in: str | None
    clock_out: str | None
    worked_minutes: int
    overtime_minutes: int
    note: str | None
    model_config = _Cfg(from_attributes=True)


@router.get("/attendance", response_model=list[AttendanceOut])
def list_attendance(
    employee_id: int | None = None,
    period: str | None = None,  # "YYYY-MM"
    db: Session = Depends(get_db),
):
    q = db.query(Attendance)
    if employee_id is not None:
        q = q.filter(Attendance.employee_id == employee_id)
    if period and len(period) == 7:
        from datetime import date as _D2

        try:
            year, month = int(period[:4]), int(period[5:])
        except ValueError:
            raise HTTPException(status_code=400, detail="bad period")
        if month == 12:
            end = _D2(year + 1, 1, 1)
        else:
            end = _D2(year, month + 1, 1)
        q = q.filter(Attendance.date >= _D2(year, month, 1), Attendance.date < end)
    return q.order_by(Attendance.date.desc(), Attendance.employee_id).all()


@router.post("/attendance/clock-in", response_model=AttendanceOut)
def clock_in(payload: AttendanceClockIn, db: Session = Depends(get_db)):
    today = payload.date or _date.today()
    now_t = payload.time or _dt.now().strftime("%H:%M:%S")
    row = (
        db.query(Attendance)
        .filter(Attendance.employee_id == payload.employee_id, Attendance.date == today)
        .with_for_update()
        .first()
    )
    if row:
        if row.clock_in:
            raise HTTPException(status_code=400, detail="Already clocked in today")
        row.clock_in = now_t
    else:
        row = Attendance(
            employee_id=payload.employee_id, date=today, clock_in=now_t
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/attendance/clock-out", response_model=AttendanceOut)
def clock_out(payload: AttendanceClockOut, db: Session = Depends(get_db)):
    today = payload.date or _date.today()
    now_t = payload.time or _dt.now().strftime("%H:%M:%S")
    row = (
        db.query(Attendance)
        .filter(Attendance.employee_id == payload.employee_id, Attendance.date == today)
        .with_for_update()
        .first()
    )
    if not row or not row.clock_in:
        raise HTTPException(status_code=400, detail="Clock in first")
    row.clock_out = now_t
    in_min = _hms_to_min(row.clock_in)
    out_min = _hms_to_min(now_t)
    if in_min is None or out_min is None:
        raise HTTPException(status_code=400, detail="Invalid time range")
    # Cross-midnight shift: out_time earlier than in_time means next day.
    if out_min < in_min:
        out_min += 24 * 60
    worked = out_min - in_min
    # Subtract a 60-minute lunch break for shifts > 6h
    if worked > 360:
        worked -= 60
    # Overtime: anything beyond 8h on weekday; full duration on weekend/holiday
    is_weekend = today.weekday() >= 5
    is_holiday = (
        db.query(Holiday)
        .filter(Holiday.date == today, Holiday.country == "KR")
        .first()
        is not None
    )
    if is_weekend or is_holiday:
        overtime = worked
    else:
        overtime = max(0, worked - 480)
    row.worked_minutes = worked
    row.overtime_minutes = overtime
    if payload.note:
        row.note = payload.note
    db.commit()
    db.refresh(row)
    return row


@router.get("/attendance/summary")
def attendance_summary(
    employee_id: int,
    period: str,  # "YYYY-MM"
    db: Session = Depends(get_db),
):
    """Aggregate worked + overtime hours for the period."""
    rows = list_attendance(employee_id=employee_id, period=period, db=db)
    total = sum(r.worked_minutes for r in rows)
    overtime = sum(r.overtime_minutes for r in rows)
    return {
        "employee_id": employee_id,
        "period": period,
        "days": len(rows),
        "total_hours": round(total / 60, 2),
        "overtime_hours": round(overtime / 60, 2),
    }


# ---- Year-end settlement + Performance review -----------------------------


from app.modules.hr.models import (  # noqa: E402
    PerformanceReview,
    YearEndSettlement,
)


def _yes_compute_owed(taxable: _D) -> _D:
    """Annual tax = piecewise progressive Korean income tax (simplified 2026)."""
    brackets = [
        (_D("14000000"), _D("0.06"), _D("0")),
        (_D("50000000"), _D("0.15"), _D("1260000")),
        (_D("88000000"), _D("0.24"), _D("5760000")),
        (_D("150000000"), _D("0.35"), _D("15440000")),
        (_D("300000000"), _D("0.38"), _D("19940000")),
        (_D("500000000"), _D("0.40"), _D("25940000")),
        (_D("1000000000"), _D("0.42"), _D("35940000")),
    ]
    if taxable <= 0:
        return _D("0")
    for cap, rate, deduct in brackets:
        if taxable <= cap:
            return (taxable * rate - deduct).quantize(_D("1"))
    # Top bracket: 45%
    return (taxable * _D("0.45") - _D("65940000")).quantize(_D("1"))


class YESIn(_BaseModel):
    employee_id: int
    tax_year: int
    deductions: _D = _D("0")
    credits: _D = _D("0")
    notes: str | None = None


class YESOut(_BaseModel):
    id: int
    employee_id: int
    tax_year: int
    gross_annual: _D
    deductions: _D
    credits: _D
    tax_withheld: _D
    tax_owed: _D
    refund_or_due: _D
    notes: str | None
    model_config = _Cfg(from_attributes=True)


@router.post(
    "/year-end-settlement",
    response_model=YESOut,
    dependencies=[Depends(require_role("admin"))],
)
def run_year_end_settlement(payload: YESIn, db: Session = Depends(get_db)):
    """Compute year-end settlement: sum of payrolls in `tax_year`, apply
    deductions + credits, derive owed tax, refund or extra payment."""
    pays = (
        db.query(Payroll)
        .filter(
            Payroll.employee_id == payload.employee_id,
            Payroll.period_code.like(f"{payload.tax_year}-%"),
        )
        .all()
    )
    if not pays:
        raise HTTPException(
            status_code=400,
            detail=f"No payrolls for employee {payload.employee_id} in {payload.tax_year}",
        )
    gross = sum(
        (_D(p.base_salary) + _D(p.bonus) + _D(p.allowance) for p in pays),
        _D("0"),
    )
    withheld = sum((_D(p.income_tax) for p in pays), _D("0"))
    taxable = max(_D("0"), gross - _D(payload.deductions))
    owed = _yes_compute_owed(taxable)
    after_credit = max(_D("0"), owed - _D(payload.credits))
    refund = withheld - after_credit  # 양수=환급, 음수=추가납부

    existing = (
        db.query(YearEndSettlement)
        .filter(
            YearEndSettlement.employee_id == payload.employee_id,
            YearEndSettlement.tax_year == payload.tax_year,
        )
        .with_for_update()
        .first()
    )
    if existing:
        existing.gross_annual = gross
        existing.deductions = payload.deductions
        existing.credits = payload.credits
        existing.tax_withheld = withheld
        existing.tax_owed = after_credit
        existing.refund_or_due = refund
        existing.notes = payload.notes
        yes = existing
    else:
        yes = YearEndSettlement(
            employee_id=payload.employee_id, tax_year=payload.tax_year,
            gross_annual=gross, deductions=payload.deductions, credits=payload.credits,
            tax_withheld=withheld, tax_owed=after_credit, refund_or_due=refund,
            notes=payload.notes,
        )
        db.add(yes)
    db.commit()
    db.refresh(yes)
    return yes


@router.get("/year-end-settlement", response_model=list[YESOut])
def list_year_end(
    tax_year: int | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(YearEndSettlement)
    if tax_year is not None:
        q = q.filter(YearEndSettlement.tax_year == tax_year)
    if employee_id is not None:
        q = q.filter(YearEndSettlement.employee_id == employee_id)
    return q.order_by(YearEndSettlement.tax_year.desc(), YearEndSettlement.employee_id).all()


# ---- Performance reviews --------------------------------------------------


import json as _json2  # noqa: E402


class KPIScore(_BaseModel):
    kpi: str
    target: float
    actual: float
    score: int  # 1-5


class ReviewIn(_BaseModel):
    employee_id: int
    period_code: str
    overall_rating: int | None = None
    kpi_scores: list[KPIScore] = []
    comments: str | None = None
    finalize: bool = False


class ReviewOut(_BaseModel):
    id: int
    employee_id: int
    period_code: str
    reviewer_id: int | None
    overall_rating: int | None
    kpi_scores: list[dict]
    comments: str | None
    finalized_at: _date | None
    model_config = _Cfg(from_attributes=True)


def _review_to_out(r: PerformanceReview) -> dict:
    return {
        "id": r.id, "employee_id": r.employee_id, "period_code": r.period_code,
        "reviewer_id": r.reviewer_id, "overall_rating": r.overall_rating,
        "kpi_scores": _json2.loads(r.kpi_scores) if r.kpi_scores else [],
        "comments": r.comments, "finalized_at": r.finalized_at,
    }


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    employee_id: int | None = None,
    period_code: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(PerformanceReview).order_by(PerformanceReview.period_code.desc())
    if employee_id is not None:
        q = q.filter(PerformanceReview.employee_id == employee_id)
    if period_code:
        q = q.filter(PerformanceReview.period_code == period_code)
    return [_review_to_out(r) for r in q.all()]


@router.post(
    "/reviews",
    response_model=ReviewOut,
    dependencies=[Depends(require_role("manager"))],
)
def upsert_review(
    payload: ReviewIn,
    db: Session = Depends(get_db),
    user: _User = Depends(get_current_user),
):
    if payload.overall_rating is not None and not (1 <= payload.overall_rating <= 5):
        raise HTTPException(status_code=400, detail="overall_rating must be 1-5")
    existing = (
        db.query(PerformanceReview)
        .filter(
            PerformanceReview.employee_id == payload.employee_id,
            PerformanceReview.period_code == payload.period_code,
        )
        .with_for_update()
        .first()
    )
    if existing and existing.finalized_at is not None:
        raise HTTPException(status_code=400, detail="Review already finalized")
    if existing:
        existing.overall_rating = payload.overall_rating
        existing.kpi_scores = _json2.dumps([k.model_dump() for k in payload.kpi_scores])
        existing.comments = payload.comments
        existing.reviewer_id = user.id
        if payload.finalize:
            existing.finalized_at = _date.today()
        r = existing
    else:
        r = PerformanceReview(
            employee_id=payload.employee_id, period_code=payload.period_code,
            reviewer_id=user.id, overall_rating=payload.overall_rating,
            kpi_scores=_json2.dumps([k.model_dump() for k in payload.kpi_scores]),
            comments=payload.comments,
            finalized_at=_date.today() if payload.finalize else None,
        )
        db.add(r)
    db.commit()
    db.refresh(r)
    return _review_to_out(r)
