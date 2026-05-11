from datetime import date
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class Framework(str, PyEnum):
    soc2 = "soc2"
    iso27001 = "iso27001"
    pipa = "pipa"        # 개인정보보호법
    gdpr = "gdpr"
    other = "other"


class ControlStatus(str, PyEnum):
    implemented = "implemented"
    partial = "partial"
    not_implemented = "not_implemented"


class TestResult(str, PyEnum):
    pass_ = "pass"
    fail = "fail"
    not_applicable = "not_applicable"


class Control(BaseEntity):
    """A compliance control mapped to one or more frameworks."""

    __tablename__ = "compliance_controls"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework: Mapped[Framework] = mapped_column(
        Enum(Framework), nullable=False, index=True
    )
    category: Mapped[str | None] = mapped_column(String(100))  # access, change_mgmt, ...
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ControlStatus] = mapped_column(
        Enum(ControlStatus), default=ControlStatus.not_implemented,
        nullable=False, index=True,
    )
    evidence_url: Mapped[str | None] = mapped_column(String(500))
    test_frequency_days: Mapped[int] = mapped_column(Integer, default=90)


class ControlTest(BaseEntity):
    """An evidence-gathering test against a control."""

    __tablename__ = "compliance_control_tests"

    control_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_controls.id"), nullable=False, index=True
    )
    tested_at: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    tester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    result: Mapped[TestResult] = mapped_column(
        Enum(TestResult), default=TestResult.not_applicable, nullable=False
    )
    findings: Mapped[str | None] = mapped_column(String(4000))
    evidence_url: Mapped[str | None] = mapped_column(String(500))
