"""E-tax invoice CRUD + Hometax submission (mockable adapter)."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.etax.models import ETaxInvoice, ETaxStatus, ETaxType

router = APIRouter(
    prefix="/api/etax",
    tags=["etax"],
    dependencies=[Depends(get_current_internal_user)],
)


# ---- Hometax adapter -------------------------------------------------------


class HometaxAdapter:
    """Default no-op adapter — call site stubs the network round-trip.

    A production deployment swaps this for a real implementation that wraps
    the NTS Hometax API. Validations live in `_validate` so they run no matter
    which adapter is active.
    """

    def submit(self, inv: ETaxInvoice) -> tuple[bool, str, str | None]:
        """Returns (ok, message, nts_no_if_accepted)."""
        self._validate(inv)
        # Mock NTS approval number — production replaces this.
        nts_no = f"NTS-{inv.issued_date.isoformat()}-{inv.id:06d}"
        return True, "Mock submission accepted", nts_no

    @staticmethod
    def _validate(inv: ETaxInvoice) -> None:
        if not _is_business_no(inv.supplier_business_no):
            raise HTTPException(status_code=400, detail="Bad supplier_business_no")
        if not _is_business_no(inv.buyer_business_no):
            raise HTTPException(status_code=400, detail="Bad buyer_business_no")
        if Decimal(inv.subtotal) + Decimal(inv.tax) != Decimal(inv.total):
            raise HTTPException(
                status_code=400, detail="subtotal + tax != total"
            )


def _is_business_no(s: str) -> bool:
    """Validate Korean business registration number with the NTS check digit."""
    digits = [c for c in (s or "") if c.isdigit()]
    if len(digits) != 10:
        return False
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    s_sum = sum(int(digits[i]) * weights[i] for i in range(9))
    s_sum += (int(digits[8]) * 5) // 10
    check = (10 - s_sum % 10) % 10
    return check == int(digits[9])


_adapter: HometaxAdapter = HometaxAdapter()


def use_adapter(adapter: HometaxAdapter) -> None:
    """Test/runtime hook — swap the live adapter."""
    global _adapter
    _adapter = adapter


# ---- Schemas ---------------------------------------------------------------


class ETaxIn(BaseModel):
    type: ETaxType
    invoice_id: int | None = None
    supplier_invoice_id: int | None = None
    issued_date: date
    supplier_business_no: str
    supplier_name: str
    buyer_business_no: str
    buyer_name: str
    item_summary: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal


class ETaxOut(ETaxIn):
    id: int
    nts_no: str | None
    status: ETaxStatus
    submitted_at: datetime | None
    response_message: str | None
    model_config = ConfigDict(from_attributes=True)


# ---- Endpoints -------------------------------------------------------------


@router.get("", response_model=Page[ETaxOut])
def list_etax(
    type: ETaxType | None = None,
    status: ETaxStatus | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    q = db.query(ETaxInvoice).order_by(ETaxInvoice.issued_date.desc())
    if type:
        q = q.filter(ETaxInvoice.type == type)
    if status:
        q = q.filter(ETaxInvoice.status == status)
    return paginate(q, params)


@router.post(
    "",
    response_model=ETaxOut,
    dependencies=[Depends(require_role("staff"))],
)
def create_etax(payload: ETaxIn, db: Session = Depends(get_db)):
    if Decimal(payload.subtotal) + Decimal(payload.tax) != Decimal(payload.total):
        raise HTTPException(status_code=400, detail="subtotal + tax != total")
    inv = ETaxInvoice(**payload.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/{etax_id}/submit",
    response_model=ETaxOut,
    dependencies=[Depends(require_role("manager"))],
)
def submit_etax(etax_id: int, db: Session = Depends(get_db)):
    inv = (
        db.query(ETaxInvoice)
        .filter(ETaxInvoice.id == etax_id)
        .with_for_update()
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if inv.status != ETaxStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot submit from {inv.status.value}")
    try:
        ok, msg, nts_no = _adapter.submit(inv)
    except HTTPException:
        raise
    except Exception as exc:
        inv.status = ETaxStatus.rejected
        inv.response_message = f"Adapter error: {exc}"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    inv.submitted_at = datetime.utcnow()
    inv.response_message = msg
    if ok:
        inv.nts_no = nts_no
        inv.status = ETaxStatus.accepted
    else:
        inv.status = ETaxStatus.rejected
    db.commit()
    db.refresh(inv)
    return inv


@router.post(
    "/{etax_id}/cancel",
    response_model=ETaxOut,
    dependencies=[Depends(require_role("admin"))],
)
def cancel_etax(etax_id: int, db: Session = Depends(get_db)):
    inv = db.query(ETaxInvoice).filter(ETaxInvoice.id == etax_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    inv.status = ETaxStatus.cancelled
    db.commit()
    db.refresh(inv)
    return inv
