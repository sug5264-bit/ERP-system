from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.db import get_db
from app.modules.currencies import service
from app.modules.currencies.models import Currency, ExchangeRate
from app.modules.currencies.schemas import (
    ConvertResult,
    CurrencyCreate,
    CurrencyOut,
    ExchangeRateIn,
    ExchangeRateOut,
)

router = APIRouter(
    prefix="/api/currencies",
    tags=["currencies"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[CurrencyOut])
def list_currencies(db: Session = Depends(get_db)):
    return db.query(Currency).order_by(Currency.code).all()


@router.post(
    "",
    response_model=CurrencyOut,
    dependencies=[Depends(require_role("admin"))],
)
def create_currency(payload: CurrencyCreate, db: Session = Depends(get_db)):
    if db.query(Currency).filter(Currency.code == payload.code.upper()).first():
        raise HTTPException(status_code=400, detail="Code already exists")
    if payload.is_base:
        # ensure only one base
        for c in db.query(Currency).filter(Currency.is_base.is_(True)).all():
            c.is_base = False
    cur = Currency(**{**payload.model_dump(), "code": payload.code.upper()})
    db.add(cur)
    db.commit()
    db.refresh(cur)
    return cur


@router.get("/{code}/rates", response_model=list[ExchangeRateOut])
def list_rates(code: str, db: Session = Depends(get_db)):
    cur = service.get_currency(db, code)
    if not cur:
        raise HTTPException(status_code=404, detail="Unknown currency")
    return (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency_id == cur.id)
        .order_by(ExchangeRate.as_of_date.desc())
        .all()
    )


@router.post(
    "/{code}/rates",
    response_model=ExchangeRateOut,
    dependencies=[Depends(require_role("admin"))],
)
def add_rate(code: str, payload: ExchangeRateIn, db: Session = Depends(get_db)):
    cur = service.get_currency(db, code)
    if not cur:
        raise HTTPException(status_code=404, detail="Unknown currency")
    rate = ExchangeRate(
        currency_id=cur.id,
        rate_to_base=payload.rate_to_base,
        as_of_date=payload.as_of_date or date.today(),
    )
    # upsert behaviour for the same date
    existing = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.currency_id == cur.id,
            ExchangeRate.as_of_date == rate.as_of_date,
        )
        .first()
    )
    if existing:
        existing.rate_to_base = payload.rate_to_base
        db.commit()
        db.refresh(existing)
        return existing
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate


@router.get("/convert", response_model=ConvertResult)
def convert(
    amount: Decimal = Query(..., gt=0),
    from_: str = Query(..., alias="from", min_length=3, max_length=3),
    to: str = Query(..., min_length=3, max_length=3),
    db: Session = Depends(get_db),
):
    try:
        converted, rate_used, rate_date = service.convert(db, amount, from_, to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ConvertResult(
        amount=amount,
        from_currency=from_.upper(),
        to_currency=to.upper(),
        converted=converted,
        rate_used=rate_used,
        as_of_date=rate_date,
    )
