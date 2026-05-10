"""Data-subject request handling + retention policy + PII access bundle."""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.privacy.models import (
    DataSubjectRequest,
    DSRStatus,
    DSRType,
    RetentionPolicy,
)


router = APIRouter(
    prefix="/api/privacy",
    tags=["privacy"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- DSR -------------------------------------------------------------------


class DSRIn(BaseModel):
    type: DSRType
    subject_email: EmailStr
    subject_name: str | None = None
    description: str | None = None


class DSROut(BaseModel):
    id: int
    type: DSRType
    subject_email: str
    subject_name: str | None
    description: str | None
    status: DSRStatus
    received_at: datetime
    due_at: date | None
    completed_at: datetime | None
    handled_by_id: int | None
    response_notes: str | None
    model_config = ConfigDict(from_attributes=True)


@router.get("/requests", response_model=list[DSROut])
def list_requests(
    status: DSRStatus | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(DataSubjectRequest).order_by(DataSubjectRequest.received_at.desc())
    if status:
        q = q.filter(DataSubjectRequest.status == status)
    return q.all()


@router.post("/requests", response_model=DSROut)
def create_request(payload: DSRIn, db: Session = Depends(get_db)):
    """Anyone authenticated may file a DSR. PIPA: response due in 10 days."""
    req = DataSubjectRequest(
        type=payload.type,
        subject_email=payload.subject_email,
        subject_name=payload.subject_name,
        description=payload.description,
        due_at=date.today() + timedelta(days=10),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/requests/{req_id}/complete",
    response_model=DSROut,
    dependencies=[Depends(require_role("admin"))],
)
def complete_request(
    req_id: int,
    response_notes: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    req = (
        db.query(DataSubjectRequest)
        .filter(DataSubjectRequest.id == req_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    if req.status == DSRStatus.completed:
        raise HTTPException(status_code=400, detail="Already completed")
    req.status = DSRStatus.completed
    req.completed_at = datetime.utcnow()
    req.handled_by_id = user.id
    req.response_notes = response_notes
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/requests/{req_id}/reject",
    response_model=DSROut,
    dependencies=[Depends(require_role("admin"))],
)
def reject_request(
    req_id: int,
    reason: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    req = (
        db.query(DataSubjectRequest)
        .filter(DataSubjectRequest.id == req_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    req.status = DSRStatus.rejected
    req.handled_by_id = user.id
    req.response_notes = reason
    db.commit()
    db.refresh(req)
    return req


# ---- Personal data bundle (Article 15 access) ------------------------------


@router.get(
    "/access-bundle",
    dependencies=[Depends(require_role("admin"))],
)
def access_bundle(email: str, db: Session = Depends(get_db)):
    """Aggregate every record in the system associated with `email`. The
    response is JSON; admins forward it to the data subject as required by
    PIPA Art. 35 / GDPR Art. 15."""
    bundle: dict = {"email": email, "data": {}}

    user = db.query(User).filter(User.email == email).first()
    if user:
        bundle["data"]["user"] = {
            "id": user.id,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "is_active": user.is_active,
            "totp_enabled": user.totp_enabled,
        }

    # HR employee record (if any)
    from app.modules.hr.models import Employee

    emp = db.query(Employee).filter(Employee.email == email).first()
    if emp:
        bundle["data"]["employee"] = {
            "id": emp.id,
            "employee_no": emp.employee_no,
            "full_name": emp.full_name,
            "position": emp.position,
            "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
            "salary": float(emp.salary or 0),
        }

    # Sales contact records
    from app.modules.sales.models import Customer

    customers = db.query(Customer).filter(Customer.email == email).all()
    if customers:
        bundle["data"]["customers"] = [
            {"id": c.id, "name": c.name, "company": c.company} for c in customers
        ]

    return bundle


@router.post(
    "/erase-user",
    dependencies=[Depends(require_role("admin"))],
)
def erase_user(email: str, db: Session = Depends(get_db)):
    """Erasure right (PIPA Art. 36 / GDPR Art. 17): anonymize PII fields on
    User + Employee while preserving referential integrity (audit logs,
    journal entries). The user record is deactivated; the employee email is
    rewritten to `erased+{id}@anonymized.local`."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    anon_email = f"erased+u{user.id}@anonymized.local"
    user.email = anon_email
    user.full_name = "ERASED"
    user.is_active = False
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_counter = None

    from app.modules.hr.models import Employee

    emp = db.query(Employee).filter(Employee.email == email).first()
    if emp:
        emp.email = f"erased+e{emp.id}@anonymized.local"
        emp.full_name = "ERASED"
        emp.position = None
    db.commit()
    return {"erased_email": email, "user_id": user.id, "employee_id": emp.id if emp else None}


# ---- Retention policy ------------------------------------------------------


class RetentionPolicyIn(BaseModel):
    resource_type: str
    retain_days: int
    action: str = "anonymize"
    notes: str | None = None


class RetentionPolicyOut(RetentionPolicyIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/retention", response_model=list[RetentionPolicyOut])
def list_retention(db: Session = Depends(get_db)):
    return db.query(RetentionPolicy).order_by(RetentionPolicy.resource_type).all()


@router.put(
    "/retention",
    response_model=RetentionPolicyOut,
    dependencies=[Depends(require_role("admin"))],
)
def upsert_retention(payload: RetentionPolicyIn, db: Session = Depends(get_db)):
    if payload.retain_days <= 0:
        raise HTTPException(status_code=400, detail="retain_days must be > 0")
    if payload.action not in ("anonymize", "purge"):
        raise HTTPException(status_code=400, detail="action must be anonymize|purge")
    p = (
        db.query(RetentionPolicy)
        .filter(RetentionPolicy.resource_type == payload.resource_type)
        .first()
    )
    if p:
        p.retain_days = payload.retain_days
        p.action = payload.action
        p.notes = payload.notes
    else:
        p = RetentionPolicy(**payload.model_dump())
        db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ---- PII redaction helper --------------------------------------------------


def redact_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{'*' * len(local)}@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


def redact_phone(phone: str | None) -> str | None:
    if not phone:
        return phone
    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 4:
        return "*" * len(phone)
    keep = "".join(digits[-4:])
    return f"***-****-{keep}"


@router.get("/redact-preview")
def redact_preview(email: str = "", phone: str = ""):
    """Utility endpoint to preview how a value would be redacted."""
    return {
        "email": redact_email(email) if email else None,
        "phone": redact_phone(phone) if phone else None,
    }
