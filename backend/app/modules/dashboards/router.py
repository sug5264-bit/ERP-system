"""Dashboards: a collection of report-builder widgets, executed together."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.dashboards.models import Dashboard, DashboardWidget
from app.modules.report_builder.models import ReportDefinition
from app.modules.report_builder.router import _run

router = APIRouter(
    prefix="/api/dashboards",
    tags=["dashboards"],
    dependencies=[Depends(get_current_internal_user)],
)


class WidgetIn(BaseModel):
    report_definition_id: int
    title: str
    position: int = 0
    chart_type: str = "table"


class WidgetOut(WidgetIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class DashboardIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    is_public: bool = False
    widgets: list[WidgetIn] = []


class DashboardOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    is_public: bool
    owner_id: int | None
    widgets: list[WidgetOut]
    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[DashboardOut])
def list_dashboards(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    return (
        db.query(Dashboard)
        .options(selectinload(Dashboard.widgets))
        .filter((Dashboard.is_public.is_(True)) | (Dashboard.owner_id == user.id))
        .order_by(Dashboard.code)
        .all()
    )


@router.post("", response_model=DashboardOut)
def create_dashboard(
    payload: DashboardIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    if db.query(Dashboard).filter(Dashboard.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Code exists")
    d = Dashboard(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
        owner_id=user.id,
    )
    for w in payload.widgets:
        if not db.query(ReportDefinition).filter(ReportDefinition.id == w.report_definition_id).first():
            raise HTTPException(
                status_code=400,
                detail=f"Report definition {w.report_definition_id} not found",
            )
        d.widgets.append(DashboardWidget(**w.model_dump()))
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.delete(
    "/{dashboard_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_dashboard(dashboard_id: int, db: Session = Depends(get_db)):
    d = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/{dashboard_id}/run")
def run_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_internal_user),
):
    """Execute every widget in the dashboard and return the aggregated payload.

    Each widget result is best-effort — if one fails the dashboard still
    returns with `error` set on that widget instead of a global 500.
    """
    d = (
        db.query(Dashboard)
        .options(selectinload(Dashboard.widgets))
        .filter(Dashboard.id == dashboard_id)
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    if not d.is_public and d.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your private dashboard")

    widgets_out = []
    for w in sorted(d.widgets, key=lambda x: x.position):
        defn = (
            db.query(ReportDefinition)
            .filter(ReportDefinition.id == w.report_definition_id)
            .first()
        )
        widget_payload = {
            "id": w.id,
            "title": w.title,
            "chart_type": w.chart_type,
            "position": w.position,
        }
        if not defn:
            widget_payload["error"] = "report definition deleted"
            widgets_out.append(widget_payload)
            continue
        try:
            spec = json.loads(defn.spec) if defn.spec else {}
            widget_payload["data"] = _run(spec, db)
        except HTTPException as exc:
            widget_payload["error"] = exc.detail
        except Exception as exc:
            widget_payload["error"] = str(exc)
        widgets_out.append(widget_payload)

    return {
        "dashboard": {"id": d.id, "code": d.code, "name": d.name},
        "widgets": widgets_out,
    }
