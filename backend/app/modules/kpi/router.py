"""KPI library endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user
from app.core.db import get_db
from app.modules.kpi import registry

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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
