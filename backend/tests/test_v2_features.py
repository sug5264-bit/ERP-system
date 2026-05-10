"""Smoke tests for the new domain features:
fiscal period lock, multi-warehouse moving avg, Quote→Invoice→Payment,
Payroll/Leave, BOM/WorkOrder, report builder, 2FA, audit diff.
"""
from datetime import date, timedelta
from decimal import Decimal


# --- Fiscal period ---------------------------------------------------------


def test_locked_period_blocks_journal(client, admin_auth, db_session):
    from app.modules.finance.models import (
        Account,
        AccountType,
        FiscalPeriod,
    )

    cash = Account(code="CASH", name="cash", type=AccountType.asset)
    rev = Account(code="REV", name="rev", type=AccountType.revenue)
    db_session.add_all([cash, rev])
    db_session.flush()
    p = FiscalPeriod(
        code="2026-01",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        is_closed=True,
    )
    db_session.add(p)
    db_session.commit()

    res = client.post(
        "/api/finance/journal-entries",
        headers=admin_auth["headers"],
        json={
            "entry_date": "2026-01-15",
            "description": "in locked period",
            "lines": [
                {"account_id": cash.id, "debit": 100, "credit": 0},
                {"account_id": rev.id, "debit": 0, "credit": 100},
            ],
        },
    )
    assert res.status_code == 400
    assert "마감" in res.json()["error"]["message"]


def test_close_and_reopen_period(client, admin_auth, db_session):
    from app.modules.finance.models import FiscalPeriod

    create = client.post(
        "/api/finance/periods",
        headers=admin_auth["headers"],
        json={
            "code": "2026-02",
            "start_date": "2026-02-01",
            "end_date": "2026-02-28",
        },
    )
    assert create.status_code == 200
    pid = create.json()["id"]

    close = client.post(
        f"/api/finance/periods/{pid}/close", headers=admin_auth["headers"]
    )
    assert close.status_code == 200
    assert close.json()["is_closed"] is True

    reopen = client.post(
        f"/api/finance/periods/{pid}/reopen", headers=admin_auth["headers"]
    )
    assert reopen.json()["is_closed"] is False


# --- Trial balance + Income statement -------------------------------------


def test_income_statement_computes_net(client, admin_auth, db_session):
    from app.modules.finance.models import (
        Account,
        AccountType,
        JournalEntry,
        JournalLine,
    )

    cash = Account(code="C2", name="cash", type=AccountType.asset)
    rev = Account(code="R2", name="rev", type=AccountType.revenue)
    exp = Account(code="E2", name="exp", type=AccountType.expense)
    db_session.add_all([cash, rev, exp])
    db_session.flush()
    e1 = JournalEntry(entry_date=date(2026, 3, 5), description="sale")
    e1.lines.append(JournalLine(account_id=cash.id, debit=300, credit=0))
    e1.lines.append(JournalLine(account_id=rev.id, debit=0, credit=300))
    e2 = JournalEntry(entry_date=date(2026, 3, 6), description="exp")
    e2.lines.append(JournalLine(account_id=exp.id, debit=100, credit=0))
    e2.lines.append(JournalLine(account_id=cash.id, debit=0, credit=100))
    db_session.add_all([e1, e2])
    db_session.commit()

    res = client.get(
        "/api/finance/income-statement?start=2026-03-01&end=2026-03-31",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["revenue"] == 300
    assert body["expense"] == 100
    assert body["net_income"] == 200


# --- Multi-warehouse + moving avg cost ------------------------------------


def test_moving_average_cost(client, admin_auth, db_session):
    from app.modules.inventory.models import Item, Warehouse, WarehouseStock

    item = Item(sku="MA-1", name="x", unit="EA", unit_price=Decimal("0"), stock_qty=Decimal("0"))
    wh = Warehouse(code="WH1", name="W1")
    db_session.add_all([item, wh])
    db_session.commit()

    # First inbound: 100 @ 10
    client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={
            "item_id": item.id,
            "warehouse_id": wh.id,
            "type": "inbound",
            "quantity": 100,
            "unit_cost": 10,
        },
    )
    # Second inbound: 50 @ 16  →  avg = (100*10 + 50*16) / 150 = 12
    client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={
            "item_id": item.id,
            "warehouse_id": wh.id,
            "type": "inbound",
            "quantity": 50,
            "unit_cost": 16,
        },
    )
    ws = (
        db_session.query(WarehouseStock)
        .filter(WarehouseStock.item_id == item.id, WarehouseStock.warehouse_id == wh.id)
        .first()
    )
    assert ws is not None
    assert Decimal(ws.quantity) == Decimal("150")
    # Allow tiny rounding tolerance from Decimal division
    assert abs(Decimal(ws.avg_cost) - Decimal("12")) < Decimal("0.01")


# --- Quote → Invoice → Payment --------------------------------------------


def test_quote_to_cash_flow(client, admin_auth, db_session):
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer

    item = Item(sku="QC-1", name="x", unit="EA", unit_price=Decimal("100"), stock_qty=Decimal("100"))
    cust = Customer(name="QC Buyer")
    db_session.add_all([item, cust])
    db_session.commit()

    q = client.post(
        "/api/billing/quotes",
        headers=admin_auth["headers"],
        json={
            "quote_no": "Q-1",
            "customer_id": cust.id,
            "items": [{"item_id": item.id, "quantity": 5, "unit_price": 100}],
        },
    ).json()

    conv = client.post(
        f"/api/billing/quotes/{q['id']}/convert", headers=admin_auth["headers"]
    ).json()
    assert "order_id" in conv

    inv = client.post(
        "/api/billing/invoices",
        headers=admin_auth["headers"],
        json={
            "invoice_no": "INV-1",
            "customer_id": cust.id,
            "sales_order_id": conv["order_id"],
            "items": [
                {"description": "x x5", "item_id": item.id, "quantity": 5, "unit_price": 100}
            ],
            "tax_rate": 0.10,
        },
    ).json()
    # subtotal=500, tax=50, total=550
    assert Decimal(inv["total"]) == Decimal("550.00")

    issued = client.post(
        f"/api/billing/invoices/{inv['id']}/issue", headers=admin_auth["headers"]
    ).json()
    assert issued["status"] == "issued"

    pay1 = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 200},
    ).json()
    assert pay1["amount"] == "200.00"

    pay2 = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 350},
    )
    assert pay2.status_code == 200

    # Overpay should be rejected
    over = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 1},
    )
    assert over.status_code == 400


# --- Payroll + Leave -------------------------------------------------------


def test_leave_request_and_balance(client, admin_auth, db_session):
    from app.modules.hr.models import Employee, LeaveBalance

    emp = Employee(
        employee_no="HR-1",
        full_name="A",
        email="hr1@test.com",
        hire_date=date(2024, 1, 1),
        salary=Decimal("36000000"),
    )
    db_session.add(emp)
    db_session.commit()

    req = client.post(
        "/api/hr/leave-requests",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id,
            "type": "annual",
            "start_date": "2026-04-06",  # Monday
            "end_date": "2026-04-10",  # Friday → 5 days
            "reason": "vacation",
        },
    ).json()
    assert Decimal(req["days"]) == Decimal("5.0")

    approved = client.post(
        f"/api/hr/leave-requests/{req['id']}/approve",
        headers=admin_auth["headers"],
        json={"comment": "ok"},
    ).json()
    assert approved["status"] == "approved"

    bal = (
        db_session.query(LeaveBalance)
        .filter(LeaveBalance.employee_id == emp.id, LeaveBalance.year == 2026)
        .first()
    )
    assert Decimal(bal.used_days) == Decimal("5.0")


def test_payroll_creation(client, admin_auth, db_session):
    from app.modules.hr.models import Employee

    emp = Employee(
        employee_no="HR-2",
        full_name="B",
        email="hr2@test.com",
        hire_date=date(2024, 1, 1),
        salary=Decimal("48000000"),
    )
    db_session.add(emp)
    db_session.commit()

    p = client.post(
        "/api/hr/payrolls",
        headers=admin_auth["headers"],
        json={"employee_id": emp.id, "period_code": "2026-04"},
    )
    assert p.status_code == 200
    body = p.json()
    # Base = 48,000,000 / 12 = 4,000,000
    assert Decimal(body["base_salary"]) == Decimal("4000000")
    assert Decimal(body["net_pay"]) > 0


# --- BOM + Work Order ------------------------------------------------------


def test_bom_work_order_flow(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    finished = Item(sku="FG-1", name="finished", unit="EA", unit_price=Decimal("0"), stock_qty=Decimal("0"))
    raw1 = Item(sku="RM-1", name="raw1", unit="EA", unit_price=Decimal("0"), stock_qty=Decimal("100"))
    raw2 = Item(sku="RM-2", name="raw2", unit="EA", unit_price=Decimal("0"), stock_qty=Decimal("100"))
    db_session.add_all([finished, raw1, raw2])
    db_session.commit()

    bom = client.post(
        "/api/manufacturing/boms",
        headers=admin_auth["headers"],
        json={
            "finished_item_id": finished.id,
            "output_quantity": 1,
            "components": [
                {"component_item_id": raw1.id, "quantity_per": 2},
                {"component_item_id": raw2.id, "quantity_per": 3},
            ],
        },
    ).json()

    wo = client.post(
        "/api/manufacturing/work-orders",
        headers=admin_auth["headers"],
        json={"wo_no": "WO-1", "bom_id": bom["id"], "quantity": 10},
    ).json()

    rel = client.post(
        f"/api/manufacturing/work-orders/{wo['id']}/release",
        headers=admin_auth["headers"],
    )
    assert rel.status_code == 200

    db_session.refresh(raw1)
    db_session.refresh(raw2)
    assert Decimal(raw1.stock_qty) == Decimal("80")  # 100 - 2*10
    assert Decimal(raw2.stock_qty) == Decimal("70")  # 100 - 3*10

    done = client.post(
        f"/api/manufacturing/work-orders/{wo['id']}/complete",
        headers=admin_auth["headers"],
    )
    assert done.status_code == 200
    db_session.refresh(finished)
    assert Decimal(finished.stock_qty) == Decimal("10")


# --- Report builder -------------------------------------------------------


def test_report_builder_runs_safe_query(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    db_session.add(
        Item(sku="RP-1", name="rp", unit="EA", unit_price=Decimal("100"), stock_qty=Decimal("5"))
    )
    db_session.commit()

    res = client.post(
        "/api/report-builder/run",
        headers=admin_auth["headers"],
        json={
            "data_source": "items",
            "columns": ["sku", "name", "stock_qty"],
            "filters": [{"column": "sku", "op": "like", "value": "RP-"}],
            "order_by": [{"column": "sku", "dir": "asc"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert any(r["sku"] == "RP-1" for r in body["rows"])


def test_report_builder_rejects_bad_column(client, admin_auth):
    res = client.post(
        "/api/report-builder/run",
        headers=admin_auth["headers"],
        json={
            "data_source": "items",
            "columns": ["password"],  # not whitelisted
        },
    )
    assert res.status_code == 400


# --- 2FA TOTP --------------------------------------------------------------


def test_totp_setup_and_enable(client, admin_auth, db_session):
    setup = client.post("/api/auth/2fa/setup", headers=admin_auth["headers"]).json()
    assert "secret" in setup
    assert "otpauth_url" in setup

    import pyotp

    code = pyotp.TOTP(setup["secret"]).now()
    enable = client.post(
        "/api/auth/2fa/enable",
        headers=admin_auth["headers"],
        json={"code": code},
    )
    assert enable.status_code == 200


# --- Audit diff -----------------------------------------------------------


def test_audit_diff_captures_field_changes(client, admin_auth, db_session):
    from app.modules.audit.models import AuditLog
    from app.modules.inventory.models import Item

    item = Item(sku="AD-1", name="원래", unit="EA", unit_price=Decimal("100"), stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()

    client.patch(
        f"/api/inventory/items/{item.id}",
        headers=admin_auth["headers"],
        json={"name": "변경됨", "unit_price": 250},
    )
    diff_row = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_type == "inv_items",
            AuditLog.resource_id == item.id,
            AuditLog.diff.is_not(None),
        )
        .first()
    )
    assert diff_row is not None
    import json as _json

    d = _json.loads(diff_row.diff)
    assert d["name"]["before"] == "원래"
    assert d["name"]["after"] == "변경됨"
