"""Projects + timesheet + expenses + profitability summary."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.projects.models import (
    Project,
    ProjectExpense,
    ProjectRevenue,
    ProjectStatus,
    Timesheet,
)

router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class ProjectIn(BaseModel):
    code: str
    name: str
    customer_id: int | None = None
    manager_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal = Decimal("0")
    notes: str | None = None


class ProjectOut(ProjectIn):
    id: int
    status: ProjectStatus
    model_config = ConfigDict(from_attributes=True)


class TimesheetIn(BaseModel):
    project_id: int
    employee_id: int
    date: date
    minutes: int
    hourly_rate: Decimal = Decimal("0")
    description: str | None = None


class TimesheetOut(TimesheetIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ExpenseIn(BaseModel):
    project_id: int
    date: date
    category: str = "material"
    description: str
    amount: Decimal


class ExpenseOut(ExpenseIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RevenueIn(BaseModel):
    project_id: int
    date: date
    description: str
    amount: Decimal
    invoice_id: int | None = None


class RevenueOut(RevenueIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---- Project endpoints -----------------------------------------------------


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    status: ProjectStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Project).order_by(Project.code)
    if status:
        q = q.filter(Project.status == status)
    return paginate(q, params)


@router.post(
    "/projects",
    response_model=ProjectOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_project(payload: ProjectIn, db: Session = Depends(get_db)):
    if db.query(Project).filter(Project.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    p = Project(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.post(
    "/projects/{project_id}/close",
    response_model=ProjectOut,
    dependencies=[Depends(require_role("manager"))],
)
def close_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).with_for_update().first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    p.status = ProjectStatus.closed
    db.commit()
    db.refresh(p)
    return p


# ---- Timesheets / Expenses / Revenue --------------------------------------


@router.post("/timesheets", response_model=TimesheetOut)
def add_timesheet(payload: TimesheetIn, db: Session = Depends(get_db)):
    if payload.minutes <= 0:
        raise HTTPException(status_code=400, detail="minutes must be > 0")
    if not db.query(Project).filter(Project.id == payload.project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    t = Timesheet(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/timesheets", response_model=list[TimesheetOut])
def list_timesheets(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Timesheet)
        .filter(Timesheet.project_id == project_id)
        .order_by(Timesheet.date.desc())
        .all()
    )


@router.post("/expenses", response_model=ExpenseOut)
def add_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    e = ProjectExpense(**payload.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ProjectExpense)
        .filter(ProjectExpense.project_id == project_id)
        .order_by(ProjectExpense.date.desc())
        .all()
    )


@router.post("/revenues", response_model=RevenueOut)
def add_revenue(payload: RevenueIn, db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    r = ProjectRevenue(**payload.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ---- Profitability ---------------------------------------------------------


@router.get("/projects/{project_id}/profitability")
def profitability(project_id: int, db: Session = Depends(get_db)):
    """Aggregate revenue vs cost (timesheets * hourly_rate + expenses)."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")

    revenue = (
        db.query(func.coalesce(func.sum(ProjectRevenue.amount), 0))
        .filter(ProjectRevenue.project_id == project_id)
        .scalar()
        or 0
    )
    expense_total = (
        db.query(func.coalesce(func.sum(ProjectExpense.amount), 0))
        .filter(ProjectExpense.project_id == project_id)
        .scalar()
        or 0
    )
    # Labor cost = sum(minutes/60 * hourly_rate)
    labor_total = (
        db.query(
            func.coalesce(
                func.sum(Timesheet.minutes * Timesheet.hourly_rate / 60), 0
            )
        )
        .filter(Timesheet.project_id == project_id)
        .scalar()
        or 0
    )
    revenue_d = Decimal(revenue)
    cost_d = Decimal(expense_total) + Decimal(labor_total)
    margin = revenue_d - cost_d
    margin_pct = float(margin / revenue_d * 100) if revenue_d > 0 else 0.0
    return {
        "project_id": p.id,
        "project_code": p.code,
        "budget": float(p.budget),
        "revenue": float(revenue_d),
        "labor_cost": float(Decimal(labor_total)),
        "expense_cost": float(Decimal(expense_total)),
        "total_cost": float(cost_d),
        "margin": float(margin),
        "margin_pct": round(margin_pct, 2),
    }
