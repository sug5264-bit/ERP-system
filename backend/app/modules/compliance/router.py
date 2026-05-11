"""Compliance controls + tests + seeded baseline framework."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, get_current_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.compliance.models import (
    Control,
    ControlStatus,
    ControlTest,
    Framework,
    TestResult,
)

router = APIRouter(
    prefix="/api/compliance",
    tags=["compliance"],
    dependencies=[Depends(get_current_internal_user)],
)


class ControlIn(BaseModel):
    code: str
    name: str
    framework: Framework
    category: str | None = None
    description: str
    owner_id: int | None = None
    test_frequency_days: int = 90
    evidence_url: str | None = None


class ControlOut(ControlIn):
    id: int
    status: ControlStatus
    model_config = ConfigDict(from_attributes=True)


class TestIn(BaseModel):
    control_id: int
    result: TestResult
    findings: str | None = None
    evidence_url: str | None = None


# ---- Controls -------------------------------------------------------------


@router.get("/controls", response_model=list[ControlOut])
def list_controls(
    framework: Framework | None = None,
    status: ControlStatus | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Control).order_by(Control.framework, Control.code)
    if framework:
        q = q.filter(Control.framework == framework)
    if status:
        q = q.filter(Control.status == status)
    return q.all()


@router.post(
    "/controls",
    response_model=ControlOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_control(payload: ControlIn, db: Session = Depends(get_db)):
    if db.query(Control).filter(Control.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    c = Control(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch(
    "/controls/{control_id}/status",
    response_model=ControlOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_control_status(
    control_id: int, status: ControlStatus, db: Session = Depends(get_db)
):
    c = db.query(Control).filter(Control.id == control_id).with_for_update().first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    c.status = status
    db.commit()
    db.refresh(c)
    return c


# ---- Tests ----------------------------------------------------------------


@router.get("/tests")
def list_tests(control_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(ControlTest).order_by(ControlTest.tested_at.desc())
    if control_id is not None:
        q = q.filter(ControlTest.control_id == control_id)
    rows = q.limit(500).all()
    return [
        {
            "id": t.id, "control_id": t.control_id,
            "tested_at": t.tested_at.isoformat(),
            "tester_id": t.tester_id,
            "result": t.result.value, "findings": t.findings,
            "evidence_url": t.evidence_url,
        }
        for t in rows
    ]


@router.post(
    "/tests",
    dependencies=[Depends(require_role("manager"))],
)
def record_test(
    payload: TestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.query(Control).filter(Control.id == payload.control_id).first():
        raise HTTPException(status_code=404, detail="Control not found")
    t = ControlTest(
        control_id=payload.control_id,
        result=payload.result,
        findings=payload.findings,
        evidence_url=payload.evidence_url,
        tester_id=user.id,
    )
    db.add(t)
    db.commit()
    return {"id": t.id, "result": t.result.value}


# ---- Dashboard ------------------------------------------------------------


@router.get("/dashboard")
def compliance_dashboard(db: Session = Depends(get_db)):
    """High-level posture per framework: implemented %, overdue tests."""
    counts = (
        db.query(
            Control.framework,
            Control.status,
            func.count(Control.id).label("c"),
        )
        .group_by(Control.framework, Control.status)
        .all()
    )
    by_fw: dict[str, dict] = {}
    for r in counts:
        fw = r.framework.value
        by_fw.setdefault(fw, {"implemented": 0, "partial": 0, "not_implemented": 0})
        by_fw[fw][r.status.value] = int(r.c)
    # Overdue tests
    today = date.today()
    overdue: list[dict] = []
    for c in db.query(Control).all():
        last = (
            db.query(ControlTest)
            .filter(ControlTest.control_id == c.id)
            .order_by(ControlTest.tested_at.desc())
            .first()
        )
        next_due = (last.tested_at if last else c.created_at.date()) + timedelta(
            days=c.test_frequency_days
        )
        if next_due < today:
            overdue.append({
                "control_id": c.id, "code": c.code,
                "framework": c.framework.value,
                "next_due": next_due.isoformat(),
                "days_overdue": (today - next_due).days,
            })

    return {
        "frameworks": [
            {
                "framework": fw,
                "implemented_pct": round(
                    counts.get("implemented", 0) /
                    max(sum(counts.values()), 1) * 100, 1,
                ),
                **counts,
            }
            for fw, counts in by_fw.items()
        ],
        "overdue_tests": overdue,
        "overdue_count": len(overdue),
    }


# ---- Baseline seed --------------------------------------------------------


@router.post(
    "/seed-baseline",
    dependencies=[Depends(require_role("admin"))],
)
def seed_baseline(db: Session = Depends(get_db)):
    """Insert a minimal SOC 2 + ISO 27001 baseline control set.
    Skips controls whose code already exists."""
    baseline = [
        # SOC 2 - Common Criteria
        ("SOC2-CC1.1", "Control Environment", Framework.soc2, "access",
         "조직은 통제 환경의 책임을 정의하고 기록한다."),
        ("SOC2-CC6.1", "Logical Access Controls", Framework.soc2, "access",
         "사용자 권한 변경/제거 절차 및 RBAC 구현."),
        ("SOC2-CC7.2", "System Monitoring", Framework.soc2, "monitoring",
         "운영 시스템 이벤트/이상 모니터링."),
        ("SOC2-CC8.1", "Change Management", Framework.soc2, "change_mgmt",
         "변경 승인/배포/롤백 절차."),
        # ISO 27001 - Annex A controls (subset)
        ("ISO-A.5.1", "Information security policies", Framework.iso27001, "policy",
         "정보보호 정책 수립 및 검토."),
        ("ISO-A.9.2", "User access management", Framework.iso27001, "access",
         "사용자 등록/등록해제 및 권한 부여 절차."),
        ("ISO-A.12.4", "Logging and monitoring", Framework.iso27001, "monitoring",
         "사용자 활동/예외/보안 이벤트 로깅."),
        ("ISO-A.18.1", "Compliance with legal requirements", Framework.iso27001, "policy",
         "관련 법규 식별 및 준수."),
        # PIPA
        ("PIPA-15", "정보주체 권리 보장", Framework.pipa, "data_rights",
         "열람/정정/삭제/이동 요청 처리 절차 (10일 이내)."),
        ("PIPA-29", "안전성 확보 조치", Framework.pipa, "security",
         "접근권한 관리, 접속기록 보관, 암호화 등 기술적/관리적 조치."),
    ]
    inserted = 0
    for code, name, fw, cat, desc in baseline:
        if db.query(Control).filter(Control.code == code).first():
            continue
        db.add(Control(
            code=code, name=name, framework=fw, category=cat,
            description=desc, test_frequency_days=90,
        ))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "total": len(baseline)}
