from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.fx.models import ExchangeRate
from app.modules.fx.service import convert as fx_convert
from app.modules.fx.service import get_rate as fx_get_rate
from app.modules.fx.service import realized_fx_diff

router = APIRouter(
    prefix="/api/fx",
    tags=["fx"],
    dependencies=[Depends(get_current_internal_user)],
)


class RateIn(BaseModel):
    date: date
    from_ccy: str
    to_ccy: str
    rate: Decimal


class RateOut(RateIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


@router.get("/rates", response_model=list[RateOut])
def list_rates(
    from_ccy: str | None = None,
    to_ccy: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(ExchangeRate).order_by(ExchangeRate.date.desc())
    if from_ccy:
        q = q.filter(ExchangeRate.from_ccy == from_ccy.upper())
    if to_ccy:
        q = q.filter(ExchangeRate.to_ccy == to_ccy.upper())
    return q.limit(500).all()


@router.post(
    "/rates",
    response_model=RateOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_rate(payload: RateIn, db: Session = Depends(get_db)):
    if payload.rate <= 0:
        raise HTTPException(status_code=400, detail="rate must be > 0")
    if payload.from_ccy == payload.to_ccy:
        raise HTTPException(status_code=400, detail="from/to currency must differ")
    existing = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.date == payload.date,
            ExchangeRate.from_ccy == payload.from_ccy.upper(),
            ExchangeRate.to_ccy == payload.to_ccy.upper(),
        )
        .first()
    )
    if existing:
        existing.rate = payload.rate
        db.commit()
        db.refresh(existing)
        return existing
    r = ExchangeRate(
        date=payload.date,
        from_ccy=payload.from_ccy.upper(),
        to_ccy=payload.to_ccy.upper(),
        rate=payload.rate,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/convert")
def convert(
    amount: float,
    from_ccy: str,
    to_ccy: str,
    as_of: date | None = None,
    db: Session = Depends(get_db),
):
    try:
        result = fx_convert(db, Decimal(str(amount)), from_ccy.upper(), to_ccy.upper(), as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    rate = fx_get_rate(db, from_ccy.upper(), to_ccy.upper(), as_of)
    return {
        "amount": float(amount),
        "from_ccy": from_ccy.upper(),
        "to_ccy": to_ccy.upper(),
        "as_of": (as_of or date.today()).isoformat(),
        "rate": float(rate) if rate else None,
        "result": float(result),
    }


@router.get("/realized-diff")
def realized_diff(
    foreign_amount: float,
    foreign_ccy: str,
    booked_at: date,
    settled_at: date,
    db: Session = Depends(get_db),
):
    """Compute realized FX gain/loss between booking and settlement dates."""
    try:
        diff = realized_fx_diff(
            db,
            foreign_amount=Decimal(str(foreign_amount)),
            foreign_ccy=foreign_ccy.upper(),
            booked_at=booked_at,
            settled_at=settled_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "foreign_amount": foreign_amount,
        "foreign_ccy": foreign_ccy.upper(),
        "booked_at": booked_at.isoformat(),
        "settled_at": settled_at.isoformat(),
        "realized_gain_loss": float(diff),
    }
