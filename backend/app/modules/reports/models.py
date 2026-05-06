from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class ReportType(str, PyEnum):
    sales_by_month = "sales_by_month"
    employees_by_department = "employees_by_department"
    top_items = "top_items"
    account_balances = "account_balances"


class Frequency(str, PyEnum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class ReportSchedule(BaseEntity):
    __tablename__ = "report_schedules"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType), nullable=False)
    frequency: Mapped[Frequency] = mapped_column(Enum(Frequency), nullable=False)
    recipients: Mapped[str] = mapped_column(String(2000), default="")  # comma-separated emails
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    enabled: Mapped[int] = mapped_column(Integer, default=1)  # 0/1 for SQLite simplicity
