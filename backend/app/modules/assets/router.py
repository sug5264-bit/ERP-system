"""Fixed asset CRUD + monthly depreciation run.

The depreciation engine is idempotent per (asset, period_code) pair, so
running it twice for the same month does nothing the second time. Each entry
is also linked to a GL journal entry (Dr 감가상각비 / Cr 감가상각누계액) when
the matching accounts exist.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, get_current_user, require_role
from app.modules.auth.models import User
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.assets.models import (
    Asset,
    AssetCategory,
    AssetStatus,
    DepreciationEntry,
    DepreciationMethod,
)

router = APIRouter(
    prefix="/api/assets",
    tags=["assets"],
    dependencies=[Depends(get_current_internal_user)],
)


class AssetCategoryIn(BaseModel):
    code: str
    name: str
    default_useful_life_months: int = 60
    default_method: DepreciationMethod = DepreciationMethod.straight_line


class AssetCategoryOut(AssetCategoryIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class AssetIn(BaseModel):
    asset_no: str
    name: str
    category_id: int | None = None
    acquired_date: date
    acquired_cost: Decimal
    salvage_value: Decimal = Decimal("0")
    useful_life_months: int
    method: DepreciationMethod = DepreciationMethod.straight_line
    notes: str | None = None


class AssetOut(BaseModel):
    id: int
    asset_no: str
    name: str
    category_id: int | None
    acquired_date: date
    acquired_cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    method: DepreciationMethod
    accumulated_depreciation: Decimal
    book_value: Decimal
    status: AssetStatus
    disposed_date: date | None
    notes: str | None
    model_config = ConfigDict(from_attributes=True)


def _to_out(a: Asset) -> AssetOut:
    book = Decimal(a.acquired_cost) - Decimal(a.accumulated_depreciation)
    return AssetOut(
        id=a.id,
        asset_no=a.asset_no,
        name=a.name,
        category_id=a.category_id,
        acquired_date=a.acquired_date,
        acquired_cost=Decimal(a.acquired_cost),
        salvage_value=Decimal(a.salvage_value),
        useful_life_months=a.useful_life_months,
        method=a.method,
        accumulated_depreciation=Decimal(a.accumulated_depreciation),
        book_value=book,
        status=a.status,
        disposed_date=a.disposed_date,
        notes=a.notes,
    )


# ---- Categories -----------------------------------------------------------


@router.get("/categories", response_model=list[AssetCategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.query(AssetCategory).order_by(AssetCategory.code).all()


@router.post(
    "/categories",
    response_model=AssetCategoryOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_category(payload: AssetCategoryIn, db: Session = Depends(get_db)):
    if db.query(AssetCategory).filter(AssetCategory.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    c = AssetCategory(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---- Assets ----------------------------------------------------------------


@router.get("/assets", response_model=Page[AssetOut])
def list_assets(
    status: AssetStatus | None = AssetStatus.active,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    """List assets. Defaults to active-only; pass `status=` empty for all."""
    q = db.query(Asset).order_by(Asset.asset_no)
    if status is not None:
        q = q.filter(Asset.status == status)
    page = paginate(q, params)
    page["items"] = [_to_out(a) for a in page["items"]]
    return page


@router.post(
    "/assets",
    response_model=AssetOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_asset(payload: AssetIn, db: Session = Depends(get_db)):
    if db.query(Asset).filter(Asset.asset_no == payload.asset_no).first():
        raise HTTPException(status_code=400, detail="Asset no already exists")
    if payload.useful_life_months <= 0:
        raise HTTPException(status_code=400, detail="useful_life_months must be > 0")
    a = Asset(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.post(
    "/assets/{asset_id}/dispose",
    response_model=AssetOut,
    dependencies=[Depends(require_role("admin"))],
)
def dispose_asset(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).with_for_update().first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if a.status == AssetStatus.disposed:
        raise HTTPException(status_code=400, detail="Already disposed")
    a.status = AssetStatus.disposed
    a.disposed_date = date.today()
    db.commit()
    db.refresh(a)
    return _to_out(a)


# ---- Depreciation ----------------------------------------------------------


def _monthly_amount(asset: Asset) -> Decimal:
    cost = Decimal(asset.acquired_cost)
    salvage = Decimal(asset.salvage_value)
    accum = Decimal(asset.accumulated_depreciation)
    remaining = cost - accum - salvage
    if remaining <= 0:
        return Decimal("0")
    if asset.method == DepreciationMethod.straight_line:
        # Depreciable base / useful life. Stops when book value hits salvage.
        per_month = ((cost - salvage) / Decimal(asset.useful_life_months)).quantize(
            Decimal("0.01")
        )
        return min(per_month, remaining)
    # declining_balance: 2x straight-line rate per month, applied to book value
    rate = Decimal("2") / Decimal(asset.useful_life_months)
    book = cost - accum
    amount = (book * rate).quantize(Decimal("0.01"))
    return min(amount, remaining)


@router.post(
    "/depreciation/run",
    dependencies=[Depends(require_role("admin"))],
)
def run_depreciation(period_code: str, db: Session = Depends(get_db)):
    """Run depreciation for `period_code` (YYYY-MM). Idempotent — re-running
    skips assets that already have an entry for this period.

    Returns a summary: total amount, # of new entries, # skipped.
    """
    if len(period_code) != 7 or period_code[4] != "-":
        raise HTTPException(status_code=400, detail="period_code must be YYYY-MM")
    try:
        year, month = int(period_code[:4]), int(period_code[5:])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period_code")

    assets = (
        db.query(Asset)
        .filter(Asset.status == AssetStatus.active)
        .with_for_update()
        .all()
    )
    new_entries = 0
    skipped = 0
    total = Decimal("0")

    for asset in assets:
        already = (
            db.query(DepreciationEntry)
            .filter(
                DepreciationEntry.asset_id == asset.id,
                DepreciationEntry.period_code == period_code,
            )
            .first()
        )
        if already:
            skipped += 1
            continue
        amount = _monthly_amount(asset)
        if amount <= 0:
            skipped += 1
            continue
        # Auto-post: Dr 감가상각비(5200) / Cr 감가상각누계액(1390).
        # If both accounts exist we MUST post; failure aborts this asset's
        # depreciation so accumulated_depreciation stays in sync with the GL.
        # If either account is missing the post is a no-op (je_id=None).
        from app.modules.finance.models import Account, JournalEntry, JournalLine

        dep_exp = db.query(Account).filter(Account.code == "5200").first()
        accum_acc = db.query(Account).filter(Account.code == "1390").first()
        je_id: int | None = None
        if dep_exp and accum_acc:
            je = JournalEntry(
                entry_date=date(year, month, 1),
                description=f"Depreciation {asset.asset_no} {period_code}",
                reference=f"DEP-{asset.asset_no}-{period_code}",
            )
            je.lines.append(
                JournalLine(account_id=dep_exp.id, debit=amount, credit=Decimal("0"))
            )
            je.lines.append(
                JournalLine(account_id=accum_acc.id, debit=Decimal("0"), credit=amount)
            )
            db.add(je)
            db.flush()
            je_id = je.id

        entry = DepreciationEntry(
            asset_id=asset.id,
            period_code=period_code,
            amount=amount,
            journal_entry_id=je_id,
        )
        db.add(entry)
        asset.accumulated_depreciation = Decimal(asset.accumulated_depreciation) + amount
        total += amount
        new_entries += 1

    db.commit()
    return {
        "period_code": period_code,
        "new_entries": new_entries,
        "skipped": skipped,
        "total_amount": float(total),
    }


@router.get("/depreciation")
def list_depreciation(
    period_code: str | None = None,
    asset_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(DepreciationEntry).order_by(
        DepreciationEntry.period_code.desc(), DepreciationEntry.asset_id
    )
    if period_code:
        q = q.filter(DepreciationEntry.period_code == period_code)
    if asset_id is not None:
        q = q.filter(DepreciationEntry.asset_id == asset_id)
    return [
        {
            "id": e.id,
            "asset_id": e.asset_id,
            "period_code": e.period_code,
            "amount": float(e.amount),
            "journal_entry_id": e.journal_entry_id,
        }
        for e in q.all()
    ]


# ---- Transfers + Audits ---------------------------------------------------


from datetime import date as _dateT  # noqa: E402

from app.modules.assets.models import (  # noqa: E402
    AssetAudit,
    AssetAuditFinding,
    AssetAuditStatus,
    AssetTransfer,
)


class TransferIn(BaseModel):
    asset_id: int
    from_custodian_id: int | None = None
    to_custodian_id: int
    from_location: str | None = None
    to_location: str
    transfer_date: _dateT | None = None
    reason: str | None = None


class TransferOut(TransferIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class AuditIn(BaseModel):
    code: str
    started_at: _dateT | None = None
    notes: str | None = None


class FindingIn(BaseModel):
    asset_id: int
    found_present: bool
    location_match: bool = True
    condition: str | None = None
    notes: str | None = None


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    asset_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(AssetTransfer).order_by(AssetTransfer.transfer_date.desc())
    if asset_id is not None:
        q = q.filter(AssetTransfer.asset_id == asset_id)
    return q.all()


@router.post(
    "/transfers",
    response_model=TransferOut,
    dependencies=[Depends(require_role("manager"))],
)
def create_transfer(payload: TransferIn, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == payload.asset_id).with_for_update().first()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found")
    if a.status != AssetStatus.active:
        raise HTTPException(status_code=400, detail=f"Cannot transfer {a.status.value} asset")
    t = AssetTransfer(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/audits")
def list_audits(db: Session = Depends(get_db)):
    return [
        {
            "id": x.id, "code": x.code,
            "started_at": x.started_at.isoformat(),
            "closed_at": x.closed_at.isoformat() if x.closed_at else None,
            "status": x.status.value,
            "auditor_id": x.auditor_id,
        }
        for x in db.query(AssetAudit).order_by(AssetAudit.started_at.desc()).all()
    ]


@router.post(
    "/audits",
    dependencies=[Depends(require_role("admin"))],
)
def create_audit(
    payload: AuditIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.query(AssetAudit).filter(AssetAudit.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    a = AssetAudit(
        code=payload.code,
        started_at=payload.started_at or _dateT.today(),
        auditor_id=user.id,
        notes=payload.notes,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    # Auto-seed findings: one row per active asset (expected_present=True, found=False)
    active_assets = db.query(Asset).filter(Asset.status == AssetStatus.active).all()
    for ast in active_assets:
        db.add(AssetAuditFinding(
            audit_id=a.id, asset_id=ast.id,
            expected_present=True, found_present=False,
        ))
    db.commit()
    return {"id": a.id, "code": a.code, "expected_findings": len(active_assets)}


@router.get("/audits/{aid}/findings")
def list_findings(aid: int, db: Session = Depends(get_db)):
    rows = (
        db.query(AssetAuditFinding)
        .filter(AssetAuditFinding.audit_id == aid)
        .order_by(AssetAuditFinding.asset_id)
        .all()
    )
    return [
        {
            "id": r.id, "asset_id": r.asset_id,
            "expected_present": r.expected_present,
            "found_present": r.found_present,
            "location_match": r.location_match,
            "condition": r.condition, "notes": r.notes,
        }
        for r in rows
    ]


@router.post(
    "/audits/{aid}/findings",
    dependencies=[Depends(require_role("staff"))],
)
def record_finding(aid: int, payload: FindingIn, db: Session = Depends(get_db)):
    f = (
        db.query(AssetAuditFinding)
        .filter(
            AssetAuditFinding.audit_id == aid,
            AssetAuditFinding.asset_id == payload.asset_id,
        )
        .with_for_update()
        .first()
    )
    if not f:
        raise HTTPException(status_code=404, detail="Finding not initialized for this asset")
    f.found_present = payload.found_present
    f.location_match = payload.location_match
    f.condition = payload.condition
    f.notes = payload.notes
    db.commit()
    return {"id": f.id, "asset_id": f.asset_id, "found_present": f.found_present}


@router.post(
    "/audits/{aid}/close",
    dependencies=[Depends(require_role("admin"))],
)
def close_audit(aid: int, db: Session = Depends(get_db)):
    """Close audit; auto-dispose every expected-but-not-found asset."""
    a = db.query(AssetAudit).filter(AssetAudit.id == aid).with_for_update().first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if a.status == AssetAuditStatus.closed:
        raise HTTPException(status_code=400, detail="Already closed")
    missing = (
        db.query(AssetAuditFinding)
        .filter(
            AssetAuditFinding.audit_id == aid,
            AssetAuditFinding.expected_present.is_(True),
            AssetAuditFinding.found_present.is_(False),
        )
        .all()
    )
    disposed = 0
    for f in missing:
        ast = db.query(Asset).filter(Asset.id == f.asset_id).with_for_update().first()
        if ast and ast.status == AssetStatus.active:
            ast.status = AssetStatus.disposed
            ast.disposed_date = _dateT.today()
            disposed += 1
    a.status = AssetAuditStatus.closed
    a.closed_at = _dateT.today()
    db.commit()
    return {
        "id": a.id, "code": a.code,
        "missing_count": len(missing),
        "auto_disposed": disposed,
    }
