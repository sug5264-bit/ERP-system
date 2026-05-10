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


# ---- Admin-only edit / delete + journal void -------------------------------


from app.core.auth import require_role  # noqa: E402
from app.modules.finance.models import Account, JournalLine  # noqa: E402
from app.modules.finance.schemas import AccountUpdate  # noqa: E402


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_account(
    account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)
):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete(
    "/accounts/{account_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    if db.query(JournalLine).filter(JournalLine.account_id == account_id).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete account that has journal lines — accounting integrity required",
        )
    db.delete(acc)
    db.commit()
    return {"ok": True}


@router.post(
    "/journal-entries/{entry_id}/void",
    response_model=JournalEntryOut,
    dependencies=[Depends(require_role("admin"))],
)
def void_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    """Post a reversing journal entry. Original is preserved (audit trail).

    This is the accounting-correct way to 'undo' a posted journal — direct
    edit/delete is intentionally not exposed.
    """
    from datetime import date as _date

    from app.modules.finance.models import JournalEntry as _JE
    from app.modules.finance.models import JournalLine as _JL

    src = db.query(_JE).filter(_JE.id == entry_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if (src.reference or "").startswith("VOID-"):
        raise HTTPException(status_code=400, detail="Already a voiding entry")

    void_entry = _JE(
        entry_date=_date.today(),
        description=f"VOID: {src.description}",
        reference=f"VOID-{src.id}",
    )
    for line in src.lines:
        void_entry.lines.append(
            _JL(
                account_id=line.account_id,
                debit=line.credit,  # swap dr/cr
                credit=line.debit,
                memo=f"void of #{src.id}",
            )
        )
    db.add(void_entry)
    db.commit()
    db.refresh(void_entry)
    return void_entry
