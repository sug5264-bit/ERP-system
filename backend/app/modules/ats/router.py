"""ATS endpoints: job posting → candidate → application → interview → hire."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.ats.models import (
    Application,
    ApplicationStage,
    Candidate,
    Interview,
    JobPosting,
    JobStatus,
)
from app.modules.hr.models import Employee

router = APIRouter(
    prefix="/api/ats",
    tags=["ats"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Schemas ---------------------------------------------------------------


class JobPostingIn(BaseModel):
    code: str
    title: str
    department_id: int | None = None
    description: str | None = None
    headcount: int = 1


class JobPostingOut(JobPostingIn):
    id: int
    opened_at: object
    closed_at: object
    status: JobStatus
    model_config = ConfigDict(from_attributes=True)


class CandidateIn(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    resume_url: str | None = None
    source: str | None = None
    notes: str | None = None


class CandidateOut(CandidateIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ApplicationIn(BaseModel):
    job_posting_id: int
    candidate_id: int
    notes: str | None = None


class ApplicationOut(BaseModel):
    id: int
    job_posting_id: int
    candidate_id: int
    stage: ApplicationStage
    rating: int | None
    notes: str | None
    converted_employee_id: int | None
    model_config = ConfigDict(from_attributes=True)


class StageMoveIn(BaseModel):
    stage: ApplicationStage
    notes: str | None = None


class HireIn(BaseModel):
    employee_no: str
    salary: Decimal
    department_id: int | None = None
    position: str | None = None


class InterviewIn(BaseModel):
    application_id: int
    round_no: int = 1
    scheduled_at: datetime
    interviewer_id: int | None = None


class InterviewFeedback(BaseModel):
    rating: int
    feedback: str | None = None


# ---- Job postings ---------------------------------------------------------


@router.get("/jobs", response_model=Page[JobPostingOut])
def list_jobs(
    status: JobStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(JobPosting).order_by(JobPosting.opened_at.desc())
    if status:
        q = q.filter(JobPosting.status == status)
    return paginate(q, params)


@router.post(
    "/jobs",
    response_model=JobPostingOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_job(payload: JobPostingIn, db: Session = Depends(get_db)):
    if db.query(JobPosting).filter(JobPosting.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code exists")
    if payload.headcount <= 0:
        raise HTTPException(status_code=400, detail="headcount must be > 0")
    j = JobPosting(**payload.model_dump())
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


@router.post(
    "/jobs/{job_id}/close",
    response_model=JobPostingOut,
    dependencies=[Depends(require_role("manager"))],
)
def close_job(job_id: int, db: Session = Depends(get_db)):
    from datetime import date as _D

    j = db.query(JobPosting).filter(JobPosting.id == job_id).with_for_update().first()
    if not j:
        raise HTTPException(status_code=404, detail="Not found")
    j.status = JobStatus.filled
    j.closed_at = _D.today()
    db.commit()
    db.refresh(j)
    return j


# ---- Candidates -----------------------------------------------------------


@router.get("/candidates", response_model=Page[CandidateOut])
def list_candidates(params: PageParams = Depends(), db: Session = Depends(get_db)):
    return paginate(db.query(Candidate).order_by(Candidate.created_at.desc()), params)


@router.post("/candidates", response_model=CandidateOut)
def create_candidate(payload: CandidateIn, db: Session = Depends(get_db)):
    c = Candidate(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---- Applications ---------------------------------------------------------


@router.get("/applications", response_model=Page[ApplicationOut])
def list_applications(
    job_posting_id: int | None = None,
    stage: ApplicationStage | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(Application).order_by(Application.created_at.desc())
    if job_posting_id is not None:
        q = q.filter(Application.job_posting_id == job_posting_id)
    if stage:
        q = q.filter(Application.stage == stage)
    return paginate(q, params)


@router.post("/applications", response_model=ApplicationOut)
def create_application(payload: ApplicationIn, db: Session = Depends(get_db)):
    if not db.query(JobPosting).filter(JobPosting.id == payload.job_posting_id).first():
        raise HTTPException(status_code=404, detail="Job not found")
    if not db.query(Candidate).filter(Candidate.id == payload.candidate_id).first():
        raise HTTPException(status_code=404, detail="Candidate not found")
    if (
        db.query(Application)
        .filter(
            Application.job_posting_id == payload.job_posting_id,
            Application.candidate_id == payload.candidate_id,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Candidate already applied")
    a = Application(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.post(
    "/applications/{app_id}/move-stage",
    response_model=ApplicationOut,
    dependencies=[Depends(require_role("manager"))],
)
def move_stage(app_id: int, payload: StageMoveIn, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).with_for_update().first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if a.stage in (ApplicationStage.hired, ApplicationStage.withdrawn, ApplicationStage.rejected):
        raise HTTPException(status_code=400, detail=f"Cannot move from terminal stage {a.stage.value}")
    a.stage = payload.stage
    if payload.notes:
        a.notes = payload.notes
    db.commit()
    db.refresh(a)
    return a


@router.post(
    "/applications/{app_id}/hire",
    response_model=ApplicationOut,
    dependencies=[Depends(require_role("admin"))],
)
def hire(app_id: int, payload: HireIn, db: Session = Depends(get_db)):
    """Convert an offered candidate to an Employee record. Locks the
    application to `hired` and links converted_employee_id."""
    a = (
        db.query(Application)
        .filter(Application.id == app_id)
        .with_for_update()
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if a.stage != ApplicationStage.offer:
        raise HTTPException(status_code=400, detail=f"Must be in 'offer' stage (got {a.stage.value})")
    if a.converted_employee_id:
        raise HTTPException(status_code=400, detail="Already hired")

    cand = db.query(Candidate).filter(Candidate.id == a.candidate_id).first()
    if db.query(Employee).filter(Employee.employee_no == payload.employee_no).first():
        raise HTTPException(status_code=400, detail="employee_no already exists")
    if db.query(Employee).filter(Employee.email == cand.email).first():
        raise HTTPException(status_code=400, detail="Employee with this email already exists")

    emp = Employee(
        employee_no=payload.employee_no,
        full_name=cand.full_name,
        email=cand.email,
        position=payload.position,
        department_id=payload.department_id,
        salary=payload.salary,
    )
    db.add(emp)
    db.flush()
    a.stage = ApplicationStage.hired
    a.converted_employee_id = emp.id
    db.commit()
    db.refresh(a)
    return a


# ---- Interviews -----------------------------------------------------------


@router.get("/interviews")
def list_interviews(application_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Interview)
        .filter(Interview.application_id == application_id)
        .order_by(Interview.round_no)
        .all()
    )
    return [
        {
            "id": i.id, "application_id": i.application_id, "round_no": i.round_no,
            "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
            "interviewer_id": i.interviewer_id, "rating": i.rating,
            "feedback": i.feedback,
        }
        for i in rows
    ]


@router.post("/interviews")
def schedule_interview(payload: InterviewIn, db: Session = Depends(get_db)):
    if not db.query(Application).filter(Application.id == payload.application_id).first():
        raise HTTPException(status_code=404, detail="Application not found")
    i = Interview(**payload.model_dump())
    db.add(i)
    db.commit()
    db.refresh(i)
    return {"id": i.id, "round_no": i.round_no}


@router.post("/interviews/{iid}/feedback")
def submit_feedback(iid: int, payload: InterviewFeedback, db: Session = Depends(get_db)):
    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="rating must be 1-5")
    i = db.query(Interview).filter(Interview.id == iid).with_for_update().first()
    if not i:
        raise HTTPException(status_code=404, detail="Not found")
    i.rating = payload.rating
    i.feedback = payload.feedback
    db.commit()
    return {"ok": True}
