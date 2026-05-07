"""Lightweight inventory forecasting based on past outbound movements.

PoC implementation — simple moving average with a linear trend term.
For production, consider Prophet / statsmodels SARIMA.
"""
from app.core.time import utc_now
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user
from app.core.db import get_db
from app.modules.inventory.models import Item, MovementType, StockMovement

router = APIRouter(
    prefix="/api/forecast",
    tags=["forecast"],
    dependencies=[Depends(get_current_internal_user)],
)


def _daily_outbound(db: Session, item_id: int, days: int) -> list[tuple[date, float]]:
    since = utc_now() - timedelta(days=days)
    rows = (
        db.query(
            func.date(StockMovement.moved_at).label("d"),
            func.sum(StockMovement.quantity).label("qty"),
        )
        .filter(
            StockMovement.item_id == item_id,
            StockMovement.type == MovementType.outbound,
            StockMovement.moved_at >= since,
        )
        .group_by(func.date(StockMovement.moved_at))
        .order_by("d")
        .all()
    )
    return [(r.d if isinstance(r.d, date) else date.fromisoformat(str(r.d)), float(r.qty)) for r in rows]


def _moving_average(values: list[float], window: int = 7) -> float:
    if not values:
        return 0.0
    tail = values[-window:]
    return sum(tail) / len(tail)


def _linear_trend(values: list[float]) -> float:
    """Returns the per-step slope of a simple least-squares fit."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    return num / den


@router.get("/items/{item_id}")
def forecast_item(
    item_id: int,
    history_days: int = Query(60, ge=7, le=365),
    horizon_days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    history = _daily_outbound(db, item_id, history_days)

    # Densify: fill missing days with 0 so MA is stable
    series: dict[date, float] = {}
    today = date.today()
    cursor = today - timedelta(days=history_days)
    while cursor <= today:
        series[cursor] = 0.0
        cursor += timedelta(days=1)
    for d, q in history:
        if d in series:
            series[d] += q

    values = list(series.values())
    avg = _moving_average(values, 7)
    trend = _linear_trend(values[-30:] if len(values) >= 30 else values)

    forecast: list[dict] = []
    base = avg
    for step in range(1, horizon_days + 1):
        predicted = max(0.0, base + trend * step)
        forecast.append({"day": (today + timedelta(days=step)).isoformat(), "qty": round(predicted, 3)})

    total_predicted = sum(p["qty"] for p in forecast)
    days_of_stock = float(item.stock_qty) / avg if avg > 0 else None
    reorder_point = round(avg * 7, 2)  # 7-day buffer
    suggested_reorder = max(
        0.0,
        round(total_predicted - float(item.stock_qty) + reorder_point, 2),
    )

    return {
        "item": {"id": item.id, "sku": item.sku, "name": item.name, "stock_qty": float(item.stock_qty)},
        "history_days": history_days,
        "moving_avg_per_day": round(avg, 3),
        "trend_per_day": round(trend, 4),
        "horizon_days": horizon_days,
        "forecast": forecast,
        "predicted_total": round(total_predicted, 3),
        "days_of_stock_remaining": round(days_of_stock, 1) if days_of_stock is not None else None,
        "reorder_point": reorder_point,
        "suggested_reorder_qty": suggested_reorder,
    }
