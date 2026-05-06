"""Service for executing scheduled reports.

Generates a PDF for the schedule's report_type and emails it to recipients.
PDFs are also saved as attachments so they're downloadable from the UI.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_email_safe
from app.core.exports import render_pdf_bytes
from app.modules.reports.models import Frequency, ReportSchedule, ReportType


def _gather(db: Session, report_type: ReportType) -> tuple[list[str], list[list]]:
    from app.modules.finance.models import Account, JournalLine
    from app.modules.hr.models import Department, Employee
    from app.modules.inventory.models import Item
    from app.modules.sales.models import OrderStatus, SalesOrder
    from sqlalchemy import func

    if report_type == ReportType.sales_by_month:
        today = date.today()
        start = (today.replace(day=1) - timedelta(days=31 * 5)).replace(day=1)
        rows = (
            db.query(SalesOrder.order_date, SalesOrder.total)
            .filter(SalesOrder.order_date >= start)
            .filter(SalesOrder.status != OrderStatus.cancelled)
            .all()
        )
        buckets: dict[str, Decimal] = {}
        cursor = start
        while cursor <= today:
            buckets[cursor.strftime("%Y-%m")] = Decimal("0")
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        for d, total in rows:
            key = d.strftime("%Y-%m")
            if key in buckets:
                buckets[key] += Decimal(total)
        return ["월", "매출 합계"], [[m, float(v)] for m, v in sorted(buckets.items())]

    if report_type == ReportType.employees_by_department:
        rows = (
            db.query(Department.name, func.count(Employee.id))
            .outerjoin(Employee, Employee.department_id == Department.id)
            .group_by(Department.name)
            .all()
        )
        return ["부서", "인원"], [[name, count] for name, count in rows]

    if report_type == ReportType.top_items:
        items = db.query(Item).all()
        ranked = sorted(
            (
                [i.sku, i.name, float(Decimal(i.stock_qty) * Decimal(i.unit_price))]
                for i in items
            ),
            key=lambda r: r[2],
            reverse=True,
        )[:10]
        return ["SKU", "품목명", "재고가치"], ranked

    if report_type == ReportType.account_balances:
        rows = (
            db.query(
                Account.code,
                Account.name,
                Account.type,
                func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
            )
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .group_by(Account.id)
            .all()
        )
        return ["코드", "계정명", "유형", "잔액"], [
            [code, name, t.value if hasattr(t, "value") else str(t), float(bal)]
            for code, name, t, bal in rows
        ]

    return ["No data"], []


def _next_run(freq: Frequency, base: datetime) -> datetime:
    if freq == Frequency.daily:
        return base + timedelta(days=1)
    if freq == Frequency.weekly:
        return base + timedelta(weeks=1)
    return base + timedelta(days=30)


def run_schedule(db: Session, schedule: ReportSchedule) -> dict:
    headers, rows = _gather(db, schedule.report_type)

    pdf_bytes = render_pdf_bytes(rows, headers, schedule.name)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"{schedule.name.replace(' ', '_')}-{stamp}.pdf"
    path = upload_dir / filename
    path.write_bytes(pdf_bytes)

    sent = 0
    recipients = [r.strip() for r in (schedule.recipients or "").split(",") if r.strip()]
    body = f"예약 보고서 '{schedule.name}'를 첨부합니다. ({headers}, {len(rows)}건)"
    for to in recipients:
        if send_email_safe(to, f"[ERP] {schedule.name}", body):
            sent += 1

    schedule.last_run_at = datetime.utcnow()
    schedule.next_run_at = _next_run(schedule.frequency, schedule.last_run_at)
    db.commit()

    return {
        "schedule_id": schedule.id,
        "rows": len(rows),
        "pdf_path": str(path),
        "emails_sent": sent,
        "recipients": recipients,
    }
