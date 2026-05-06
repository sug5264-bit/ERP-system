from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.db import get_db
from app.modules.finance import service
from app.modules.finance.schemas import (
    AccountCreate,
    AccountOut,
    JournalEntryCreate,
    JournalEntryOut,
)

router = APIRouter(
    prefix="/api/finance",
    tags=["finance"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return service.list_accounts(db)


@router.post(
    "/accounts",
    response_model=AccountOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    return service.create_account(db, payload)


@router.get("/journal-entries", response_model=list[JournalEntryOut])
def list_journal_entries(db: Session = Depends(get_db)):
    return service.list_journal_entries(db)


@router.post(
    "/journal-entries",
    response_model=JournalEntryOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_journal_entry(payload: JournalEntryCreate, db: Session = Depends(get_db)):
    try:
        return service.create_journal_entry(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
