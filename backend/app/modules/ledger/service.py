"""Append + verify helpers for the supply-chain hash-chain ledger."""
import hashlib
import json

from sqlalchemy.orm import Session

from app.modules.ledger.models import LedgerEntry

GENESIS_HASH = "0" * 64


def _compute_hash(seq: int, event_type: str, payload: str, prev_hash: str) -> str:
    blob = f"{seq}|{event_type}|{payload}|{prev_hash}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def append(
    db: Session,
    *,
    event_type: str,
    payload: dict,
    resource_type: str | None = None,
    resource_id: int | None = None,
    actor_id: int | None = None,
) -> LedgerEntry:
    last = db.query(LedgerEntry).order_by(LedgerEntry.seq.desc()).first()
    seq = (last.seq + 1) if last else 1
    prev_hash = last.this_hash if last else GENESIS_HASH

    payload_json = json.dumps(payload, sort_keys=True, default=str)
    this_hash = _compute_hash(seq, event_type, payload_json, prev_hash)

    entry = LedgerEntry(
        seq=seq,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload_json,
        prev_hash=prev_hash,
        this_hash=this_hash,
        actor_id=actor_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify(db: Session) -> dict:
    """Walk the chain start→end and verify every hash matches."""
    rows = db.query(LedgerEntry).order_by(LedgerEntry.seq).all()
    prev = GENESIS_HASH
    for entry in rows:
        expected = _compute_hash(entry.seq, entry.event_type, entry.payload, prev)
        if expected != entry.this_hash or entry.prev_hash != prev:
            return {
                "valid": False,
                "broken_at_seq": entry.seq,
                "expected": expected,
                "stored": entry.this_hash,
            }
        prev = entry.this_hash
    return {"valid": True, "entries": len(rows), "tip_hash": prev}
