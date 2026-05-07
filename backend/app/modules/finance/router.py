from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_user, get_current_internal_user, require_module_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.finance import service
from app.modules.finance.models import JournalEntry
from app.modules.finance.schemas import (
    AccountCreate,
    AccountOut,
    JournalEntryCreate,
    JournalEntryOut,
)

router = APIRouter(
    prefix="/api/finance",
    tags=["finance"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return service.list_accounts(db)


@router.post(
    "/accounts",
    response_model=AccountOut,
    dependencies=[Depends(require_module_role("finance", "admin"))],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    return service.create_account(db, payload)


@router.get("/journal-entries", response_model=Page[JournalEntryOut])
def list_journal_entries(
    params: PageParams = Depends(), db: Session = Depends(get_db)
):
    q = (
        db.query(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .order_by(JournalEntry.entry_date.desc())
    )
    return paginate(q, params)


@router.post(
    "/journal-entries",
    response_model=JournalEntryOut,
    dependencies=[Depends(require_module_role("finance", "manager"))],
)
def create_journal_entry(payload: JournalEntryCreate, db: Session = Depends(get_db)):
    try:
        return service.create_journal_entry(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
