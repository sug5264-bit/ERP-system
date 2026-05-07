import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.custom_fields.models import FieldDefinition, FieldType, FieldValue

router = APIRouter(
    prefix="/api/custom-fields",
    tags=["custom_fields"],
    dependencies=[Depends(get_current_internal_user)],
)


class FieldDefIn(BaseModel):
    entity_type: str
    key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    required: bool = False


class FieldDefOut(BaseModel):
    id: int
    entity_type: str
    key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    required: bool

    class Config:
        from_attributes = True


class FieldValueIn(BaseModel):
    field_id: int
    value: str | None


class FieldValueOut(FieldValueIn):
    id: int
    entity_type: str
    entity_id: int

    class Config:
        from_attributes = True


def _to_def_out(d: FieldDefinition) -> FieldDefOut:
    return FieldDefOut(
        id=d.id,
        entity_type=d.entity_type,
        key=d.key,
        label=d.label,
        field_type=d.field_type,
        options=json.loads(d.options) if d.options else None,
        required=d.required,
    )


@router.get("/definitions", response_model=list[FieldDefOut])
def list_definitions(entity_type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(FieldDefinition)
    if entity_type:
        q = q.filter(FieldDefinition.entity_type == entity_type)
    return [_to_def_out(d) for d in q.order_by(FieldDefinition.entity_type, FieldDefinition.key).all()]


@router.post(
    "/definitions",
    response_model=FieldDefOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_definition(payload: FieldDefIn, db: Session = Depends(get_db)):
    if (
        db.query(FieldDefinition)
        .filter(
            FieldDefinition.entity_type == payload.entity_type,
            FieldDefinition.key == payload.key,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="Field already exists for this entity")
    d = FieldDefinition(
        entity_type=payload.entity_type,
        key=payload.key,
        label=payload.label,
        field_type=payload.field_type,
        options=json.dumps(payload.options) if payload.options else None,
        required=payload.required,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _to_def_out(d)


@router.delete(
    "/definitions/{def_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_definition(def_id: int, db: Session = Depends(get_db)):
    d = db.query(FieldDefinition).filter(FieldDefinition.id == def_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(FieldValue).filter(FieldValue.field_id == def_id).delete(
        synchronize_session=False
    )
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/values", response_model=list[FieldValueOut])
def list_values(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(FieldValue)
        .filter(
            FieldValue.entity_type == entity_type,
            FieldValue.entity_id == entity_id,
        )
        .all()
    )


@router.put("/values")
def upsert_values(
    entity_type: str,
    entity_id: int,
    payload: list[FieldValueIn],
    db: Session = Depends(get_db),
):
    """Upsert a batch of (field_id, value) tuples for one entity row."""
    for v in payload:
        existing = (
            db.query(FieldValue)
            .filter(
                FieldValue.entity_type == entity_type,
                FieldValue.entity_id == entity_id,
                FieldValue.field_id == v.field_id,
            )
            .first()
        )
        if existing:
            existing.value = v.value
        else:
            db.add(
                FieldValue(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_id=v.field_id,
                    value=v.value,
                )
            )
    db.commit()
    return {"ok": True}
