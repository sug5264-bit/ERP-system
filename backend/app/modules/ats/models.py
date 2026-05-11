from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import BaseEntity


class JobStatus(str, PyEnum):
    open = "open"
    on_hold = "on_hold"
    filled = "filled"
    cancelled = "cancelled"


class ApplicationStage(str, PyEnum):
    applied = "applied"
    screening = "screening"
    interview = "interview"
    offer = "offer"
    hired = "hired"
    rejected = "rejected"
    withdrawn = "withdrawn"


class JobPosting(BaseEntity):
    __tablename__ = "ats_job_postings"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("hr_departments.id"))
    description: Mapped[str | None] = mapped_column(String(4000))
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    opened_at: Mapped[date] = mapped_column(Date, default=date.today)
    closed_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.open, nullable=False, index=True
    )


class Candidate(BaseEntity):
    __tablename__ = "ats_candidates"

    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    resume_url: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(100))  # 잡코리아, 사람인, 추천, etc.
    notes: Mapped[str | None] = mapped_column(String(2000))


class Application(BaseEntity):
    __tablename__ = "ats_applications"

    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("ats_job_postings.id"), nullable=False, index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("ats_candidates.id"), nullable=False, index=True
    )
    stage: Mapped[ApplicationStage] = mapped_column(
        Enum(ApplicationStage), default=ApplicationStage.applied,
        nullable=False, index=True,
    )
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    notes: Mapped[str | None] = mapped_column(String(2000))
    converted_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("hr_employees.id")
    )

    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class Interview(BaseEntity):
    __tablename__ = "ats_interviews"

    application_id: Mapped[int] = mapped_column(
        ForeignKey("ats_applications.id"), nullable=False, index=True
    )
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    feedback: Mapped[str | None] = mapped_column(String(2000))

    application: Mapped[Application] = relationship(back_populates="interviews")
