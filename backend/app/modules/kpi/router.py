"""KPI library endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user
from app.core.db import get_db
from app.modules.kpi import registry

log = logging.getLogger("erp.kpi")

router = APIRouter(
    prefix="/api/kpi",
    tags=["kpi"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("/list")
def list_kpis():
    return {"kpis": registry.list_kpis()}


@router.get("/run/{code}")
def run_kpi(code: str, days: int = 30, db: Session = Depends(get_db)):
    """Execute a KPI by code. Pass query params via `days` etc."""
    try:
        return registry.run(code, db, params={"days": days})
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown KPI: {code}")
    except Exception:
        # Log full traceback server-side; return a generic message so DB schema
        # details and stack frames don't leak to API clients.
        log.exception("KPI %s execution failed", code)
        raise HTTPException(status_code=500, detail="KPI execution failed")
