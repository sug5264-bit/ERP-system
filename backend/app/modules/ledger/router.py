import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.ledger import service
from app.modules.ledger.models import LedgerEntry

router = APIRouter(
    prefix="/api/ledger",
    tags=["ledger"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_entries(
    limit: int = Query(100, le=500),
    offset: int = 0,
    event_type: str | None = None,
    resource_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(LedgerEntry)
    if event_type:
        q = q.filter(LedgerEntry.event_type == event_type)
    if resource_type:
        q = q.filter(LedgerEntry.resource_type == resource_type)
    rows = q.order_by(LedgerEntry.seq.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": r.id,
            "seq": r.seq,
            "event_type": r.event_type,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "payload": json.loads(r.payload),
            "prev_hash": r.prev_hash,
            "this_hash": r.this_hash,
            "actor_id": r.actor_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/verify")
def verify_chain(db: Session = Depends(get_db)):
    return service.verify(db)


@router.post("/anchor", dependencies=[Depends(require_role("admin"))])
def anchor_tip():
    """Stub: in production, post the tip_hash to an external chain (Ethereum,
    Polygon, etc) for tamper-evident off-chain notarisation. Returns the tip
    hash so an external worker can pick it up."""
    return {
        "anchor_target": "external_blockchain",
        "instructions": "Sign and submit tip_hash to your chosen ledger.",
    }


@router.post("/record")
def record_event(
    event_type: str,
    payload: dict,
    resource_type: str | None = None,
    resource_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual recording — automated writes happen from inventory & sales hooks."""
    entry = service.append(
        db,
        event_type=event_type,
        payload=payload,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=current_user.id,
    )
    return {"id": entry.id, "seq": entry.seq, "this_hash": entry.this_hash}
