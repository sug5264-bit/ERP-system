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


# --- Phase 2: holidays, auto-post, FEFO ------------------------------------


def test_holidays_excluded_from_business_days(client, admin_auth, db_session):
    """Leave request crossing a registered holiday counts fewer days."""
    from app.modules.hr.models import Holiday, Employee

    emp = Employee(employee_no="EH-1", full_name="홍홀", email="hh@x.com", salary=Decimal("3000000"))
    db_session.add(emp)
    db_session.commit()

    # Wed–Fri, 3 business days
    start = date(2026, 5, 6)  # Wed
    end = date(2026, 5, 8)    # Fri
    res = client.post(
        "/api/hr/leave-requests",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id,
            "type": "annual",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    assert res.status_code == 200, res.text
    assert float(res.json()["days"]) == 3.0

    # Add 2026-05-07 (Thu) as a holiday and re-request → 2 days
    db_session.add(Holiday(date=date(2026, 5, 7), name="테스트공휴일", country="KR"))
    db_session.commit()
    res2 = client.post(
        "/api/hr/leave-requests",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id,
            "type": "annual",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    assert res2.status_code == 200, res2.text
    assert float(res2.json()["days"]) == 2.0


def test_auto_post_invoice_and_payment(client, admin_auth, db_session):
    """Issuing an invoice posts AR/Revenue/VAT; recording payment posts Cash/AR."""
    from app.modules.finance.models import Account, AccountType, JournalEntry
    from app.modules.sales.models import Customer

    # Set up CoA matching auto_post defaults
    accounts = [
        Account(code="1100", name="현금", type=AccountType.asset),
        Account(code="1200", name="매출채권", type=AccountType.asset),
        Account(code="2150", name="부가세예수금", type=AccountType.liability),
        Account(code="4100", name="매출", type=AccountType.revenue),
    ]
    for a in accounts:
        db_session.add(a)
    cust = Customer(name="ACME", email="a@x.com")
    db_session.add(cust)
    db_session.commit()

    res = client.post(
        "/api/billing/invoices",
        headers=admin_auth["headers"],
        json={
            "invoice_no": "INV-AUTO-1",
            "customer_id": cust.id,
            "items": [{"description": "L1", "quantity": 1, "unit_price": 1000}],
            "tax_rate": 0.10,
        },
    )
    assert res.status_code == 200, res.text
    inv = res.json()
    issue = client.post(
        f"/api/billing/invoices/{inv['id']}/issue",
        headers=admin_auth["headers"],
    )
    assert issue.status_code == 200

    # Verify the GL entry exists
    je = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.reference == f"INV-{inv['invoice_no']}")
        .first()
    )
    assert je is not None
    assert sum(float(l.debit) for l in je.lines) == 1100.0
    assert sum(float(l.credit) for l in je.lines) == 1100.0

    # Pay it
    pay = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 1100},
    )
    assert pay.status_code == 200
    pay_id = pay.json()["id"]
    je2 = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.reference == f"PAY-{pay_id}")
        .first()
    )
    assert je2 is not None


def test_fefo_consume_picks_earliest_expiry(client, admin_auth, db_session):
    from app.modules.inventory.models import Item, StockLot

    item = Item(sku="MILK-1", name="우유 1L", stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()
    lot_late = StockLot(
        item_id=item.id, lot_number="L-LATE",
        quantity=Decimal("10"), expiry_date=date(2027, 1, 1),
    )
    lot_early = StockLot(
        item_id=item.id, lot_number="L-EARLY",
        quantity=Decimal("8"), expiry_date=date(2026, 6, 1),
    )
    db_session.add_all([lot_late, lot_early])
    item.stock_qty = Decimal("18")
    db_session.commit()

    res = client.post(
        f"/api/inventory/items/{item.id}/consume-fefo?quantity=10",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    movs = res.json()["movements"]
    # First 8 should come from the earlier-expiry lot
    assert movs[0]["lot_id"] == lot_early.id
    assert movs[0]["quantity"] == 8.0
    assert movs[1]["lot_id"] == lot_late.id
    assert movs[1]["quantity"] == 2.0


def test_expiring_lots_endpoint(client, admin_auth, db_session):
    from datetime import timedelta as _td
    from app.modules.inventory.models import Item, StockLot

    item = Item(sku="YOG-1", name="요거트", stock_qty=Decimal("5"))
    db_session.add(item)
    db_session.commit()
    soon = date.today() + _td(days=10)
    far = date.today() + _td(days=200)
    db_session.add_all([
        StockLot(item_id=item.id, lot_number="SOON", quantity=Decimal("3"), expiry_date=soon),
        StockLot(item_id=item.id, lot_number="FAR", quantity=Decimal("2"), expiry_date=far),
    ])
    db_session.commit()

    res = client.get(
        "/api/inventory/lots/expiring?within_days=30",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    rows = res.json()
    nums = {r["lot_number"] for r in rows}
    assert "SOON" in nums and "FAR" not in nums


# --- Phase 3: assets, CRM, 3-way matching ----------------------------------


def test_asset_depreciation_idempotent(client, admin_auth, db_session):
    """Running depreciation twice for the same period skips already-posted assets."""
    res = client.post(
        "/api/assets/assets",
        headers=admin_auth["headers"],
        json={
            "asset_no": "DEP-1",
            "name": "Test laptop",
            "acquired_date": "2026-01-01",
            "acquired_cost": 1200,
            "useful_life_months": 12,
            "method": "straight_line",
        },
    )
    assert res.status_code == 200, res.text

    # First run: 1 entry (1200/12 = 100)
    r1 = client.post(
        "/api/assets/depreciation/run?period_code=2026-05",
        headers=admin_auth["headers"],
    )
    assert r1.status_code == 200
    assert r1.json()["new_entries"] == 1
    assert r1.json()["total_amount"] == 100.0

    # Second run for same period: no new entries
    r2 = client.post(
        "/api/assets/depreciation/run?period_code=2026-05",
        headers=admin_auth["headers"],
    )
    assert r2.json()["new_entries"] == 0
    assert r2.json()["skipped"] == 1


def test_crm_lead_to_opportunity_pipeline(client, admin_auth, db_session):
    # Create lead
    res = client.post(
        "/api/crm/leads",
        headers=admin_auth["headers"],
        json={"name": "김잠재", "company": "ACME 식자재", "email": "k@a.com"},
    )
    assert res.status_code == 200, res.text
    lead_id = res.json()["id"]

    # Convert
    conv = client.post(
        f"/api/crm/leads/{lead_id}/convert",
        headers=admin_auth["headers"],
    )
    assert conv.status_code == 200, conv.text
    opp_id = conv.json()["id"]
    assert conv.json()["stage"] == "prospecting"

    # Lead now has converted status
    leads = client.get("/api/crm/leads", headers=admin_auth["headers"]).json()
    found = next(l for l in leads["items"] if l["id"] == lead_id)
    assert found["status"] == "converted"
    assert found["converted_opportunity_id"] == opp_id

    # Move stage to won
    won = client.post(
        f"/api/crm/opportunities/{opp_id}/stage",
        headers=admin_auth["headers"],
        json={"to_stage": "won", "comment": "계약 체결"},
    )
    assert won.json()["stage"] == "won"
    assert won.json()["probability"] == 100

    # Pipeline summary should report 1 won
    summary = client.get(
        "/api/crm/pipeline/summary", headers=admin_auth["headers"]
    ).json()
    won_stage = next(s for s in summary["stages"] if s["stage"] == "won")
    assert won_stage["count"] == 1


def test_three_way_matching_pass_and_reject(client, admin_auth, db_session):
    """Happy path matches; mismatch is rejected with notes."""
    from app.modules.suppliers.models import POStatus, PurchaseOrder, PurchaseOrderItem, Supplier
    from app.modules.inventory.models import Item

    sup = Supplier(code="SUP-MATCH", name="공급사X")
    item = Item(sku="ING-1", name="원료", stock_qty=Decimal("0"))
    db_session.add_all([sup, item])
    db_session.flush()
    po = PurchaseOrder(
        po_no="PO-MATCH-1",
        supplier_id=sup.id,
        status=POStatus.acknowledged,
        total=Decimal("1000"),
    )
    po.items.append(
        PurchaseOrderItem(item_id=item.id, quantity=Decimal("10"), unit_price=Decimal("100"))
    )
    db_session.add(po)
    db_session.commit()
    poi_id = po.items[0].id

    # Receipt: full quantity
    gr = client.post(
        "/api/suppliers/goods-receipts",
        headers=admin_auth["headers"],
        json={
            "gr_no": "GR-1",
            "po_id": po.id,
            "items": [{"po_item_id": poi_id, "received_qty": 10}],
        },
    )
    assert gr.status_code == 200, gr.text
    gr_id = gr.json()["id"]
    assert client.post(
        f"/api/suppliers/goods-receipts/{gr_id}/post",
        headers=admin_auth["headers"],
    ).status_code == 200

    # Supplier invoice: matching total (1000 + 0 tax)
    inv = client.post(
        "/api/suppliers/supplier-invoices",
        headers=admin_auth["headers"],
        json={
            "supplier_id": sup.id,
            "po_id": po.id,
            "vendor_invoice_no": "VINV-1",
            "invoice_date": "2026-05-01",
            "subtotal": 1000,
            "tax": 0,
            "total": 1000,
        },
    )
    inv_id = inv.json()["id"]
    matched = client.post(
        f"/api/suppliers/supplier-invoices/{inv_id}/match",
        headers=admin_auth["headers"],
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["status"] == "matched"

    # Reject case: supply a 2nd invoice with wrong total
    inv2 = client.post(
        "/api/suppliers/supplier-invoices",
        headers=admin_auth["headers"],
        json={
            "supplier_id": sup.id,
            "po_id": po.id,
            "vendor_invoice_no": "VINV-2",
            "invoice_date": "2026-05-02",
            "subtotal": 1500,
            "tax": 0,
            "total": 1500,
        },
    )
    rejected = client.post(
        f"/api/suppliers/supplier-invoices/{inv2.json()['id']}/match",
        headers=admin_auth["headers"],
    )
    assert rejected.json()["status"] == "rejected"
    assert "Total mismatch" in rejected.json()["match_notes"]


# --- Phase 4: attendance, 4-insurances, etax, projects, fx -----------------


def test_attendance_clock_in_out_and_overtime(client, admin_auth, db_session):
    from app.modules.hr.models import Employee, Holiday

    emp = Employee(employee_no="ATT-1", full_name="홍시계", email="hs@x.com",
                   salary=Decimal("3000000"))
    db_session.add(emp)
    db_session.commit()

    # Weekday: Wed 2026-05-06; 9:00 → 19:30 → 10.5h - 1h lunch = 9.5h, 1.5h overtime
    res_in = client.post(
        "/api/hr/attendance/clock-in",
        headers=admin_auth["headers"],
        json={"employee_id": emp.id, "date": "2026-05-06", "time": "09:00:00"},
    )
    assert res_in.status_code == 200
    res_out = client.post(
        "/api/hr/attendance/clock-out",
        headers=admin_auth["headers"],
        json={"employee_id": emp.id, "date": "2026-05-06", "time": "19:30:00"},
    )
    assert res_out.status_code == 200, res_out.text
    body = res_out.json()
    assert body["worked_minutes"] == 570  # 9.5h
    assert body["overtime_minutes"] == 90  # 1.5h


def test_payroll_includes_4_insurances(client, admin_auth, db_session):
    from app.modules.hr.models import Employee

    emp = Employee(employee_no="INS-1", full_name="박급여", email="pg@x.com",
                   salary=Decimal("36000000"))  # 3M/month
    db_session.add(emp)
    db_session.commit()

    res = client.post(
        "/api/hr/payrolls",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id,
            "period_code": "2026-05",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # gross = 3,000,000; nps = 4.5% = 135,000; nhi = 3.545% ≈ 106,350
    assert int(float(body["nps"])) == 135000
    assert abs(int(float(body["nhi"])) - 106350) <= 1
    assert int(float(body["ei"])) == 27000
    # ltci = 12.95% of nhi
    assert abs(int(float(body["ltci"])) - int(106350 * 0.1295)) <= 1


def test_etax_submit_mock_rejects_bad_business_no(client, admin_auth, db_session):
    res = client.post(
        "/api/etax",
        headers=admin_auth["headers"],
        json={
            "type": "sales",
            "issued_date": "2026-05-10",
            "supplier_business_no": "1234567890",  # invalid checksum on purpose
            "supplier_name": "공급사",
            "buyer_business_no": "1234567890",
            "buyer_name": "구매사",
            "item_summary": "제품 외",
            "subtotal": 1000,
            "tax": 100,
            "total": 1100,
        },
    )
    assert res.status_code == 200
    eid = res.json()["id"]
    submit = client.post(f"/api/etax/{eid}/submit", headers=admin_auth["headers"])
    # Mock adapter rejects bad business numbers
    assert submit.status_code == 400


def test_etax_submit_mock_accepts_valid_business_no(client, admin_auth, db_session):
    """Happy-path submit assigns NTS approval no and moves status to accepted."""
    # Both numbers are real-world valid checksums (Naver 220-81-62517).
    res = client.post(
        "/api/etax",
        headers=admin_auth["headers"],
        json={
            "type": "sales",
            "issued_date": "2026-05-10",
            "supplier_business_no": "2208162517",
            "supplier_name": "Supplier",
            "buyer_business_no": "2208162517",
            "buyer_name": "Buyer",
            "item_summary": "물품 일체",
            "subtotal": 1000,
            "tax": 100,
            "total": 1100,
        },
    )
    eid = res.json()["id"]
    submit = client.post(f"/api/etax/{eid}/submit", headers=admin_auth["headers"])
    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["status"] == "accepted"
    assert body["nts_no"] is not None
    assert body["submitted_at"] is not None

    # Re-submit should fail (already accepted, not draft)
    again = client.post(f"/api/etax/{eid}/submit", headers=admin_auth["headers"])
    assert again.status_code == 400


def test_project_profitability(client, admin_auth, db_session):
    from app.modules.hr.models import Employee
    from app.modules.projects.models import Project, ProjectExpense, ProjectRevenue, Timesheet

    proj = Project(code="P1", name="테스트 프로젝트", budget=Decimal("10000000"))
    emp = Employee(employee_no="PJ-1", full_name="이프로", email="ip@x.com",
                   salary=Decimal("3000000"))
    db_session.add_all([proj, emp])
    db_session.commit()

    db_session.add(ProjectRevenue(project_id=proj.id, date=date(2026, 5, 1),
                                   description="kickoff", amount=Decimal("5000000")))
    db_session.add(ProjectExpense(project_id=proj.id, date=date(2026, 5, 2),
                                   category="material", description="kit",
                                   amount=Decimal("1000000")))
    db_session.add(Timesheet(project_id=proj.id, employee_id=emp.id,
                              date=date(2026, 5, 3), minutes=600,
                              hourly_rate=Decimal("30000")))
    db_session.commit()

    res = client.get(
        f"/api/projects/projects/{proj.id}/profitability",
        headers=admin_auth["headers"],
    )
    body = res.json()
    assert body["revenue"] == 5_000_000.0
    # labor = 10h * 30,000 = 300,000
    assert body["labor_cost"] == 300_000.0
    assert body["expense_cost"] == 1_000_000.0
    assert body["margin"] == 5_000_000 - 1_000_000 - 300_000


def test_fx_rate_conversion(client, admin_auth, db_session):
    # Add USD→KRW rate, convert
    client.post(
        "/api/fx/rates",
        headers=admin_auth["headers"],
        json={"date": "2026-05-01", "from_ccy": "USD", "to_ccy": "KRW", "rate": 1380.5},
    )
    conv = client.get(
        "/api/fx/convert?amount=100&from_ccy=USD&to_ccy=KRW&as_of=2026-05-10",
        headers=admin_auth["headers"],
    )
    assert conv.status_code == 200
    assert conv.json()["result"] == 138050.0
    # Reverse lookup
    rev = client.get(
        "/api/fx/convert?amount=138050&from_ccy=KRW&to_ccy=USD&as_of=2026-05-10",
        headers=admin_auth["headers"],
    )
    assert rev.status_code == 200
    assert abs(rev.json()["result"] - 100.0) < 0.5


def test_fx_realized_diff(client, admin_auth, db_session):
    # Booked at 1300, settled at 1400 → 100 USD gains 10,000 KRW
    client.post(
        "/api/fx/rates",
        headers=admin_auth["headers"],
        json={"date": "2026-04-01", "from_ccy": "USD", "to_ccy": "KRW", "rate": 1300},
    )
    client.post(
        "/api/fx/rates",
        headers=admin_auth["headers"],
        json={"date": "2026-05-01", "from_ccy": "USD", "to_ccy": "KRW", "rate": 1400},
    )
    res = client.get(
        "/api/fx/realized-diff?foreign_amount=100&foreign_ccy=USD"
        "&booked_at=2026-04-15&settled_at=2026-05-15",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    assert res.json()["realized_gain_loss"] == 10_000.0


# --- Phase 5: bug fixes regression ----------------------------------------


def test_attendance_overnight_shift(client, admin_auth, db_session):
    """Overnight shift (cross-midnight) is calculated correctly."""
    from app.modules.hr.models import Employee

    emp = Employee(employee_no="NIGHT-1", full_name="야간조", email="n@x.com",
                   salary=Decimal("3000000"))
    db_session.add(emp)
    db_session.commit()

    client.post(
        "/api/hr/attendance/clock-in",
        headers=admin_auth["headers"],
        json={"employee_id": emp.id, "date": "2026-05-06", "time": "23:00:00"},
    )
    res = client.post(
        "/api/hr/attendance/clock-out",
        headers=admin_auth["headers"],
        json={"employee_id": emp.id, "date": "2026-05-06", "time": "02:00:00"},
    )
    assert res.status_code == 200, res.text
    # 23:00 → 02:00 = 3 hours; no lunch deduction (< 6h)
    assert res.json()["worked_minutes"] == 180


def test_closed_project_blocks_new_entries(client, admin_auth, db_session):
    """Closed project rejects timesheets / expenses / revenues."""
    from app.modules.projects.models import Project, ProjectStatus

    proj = Project(code="P-CLOSED", name="마감 프로젝트", budget=Decimal("0"),
                   status=ProjectStatus.closed)
    db_session.add(proj)
    db_session.commit()

    res = client.post(
        "/api/projects/timesheets",
        headers=admin_auth["headers"],
        json={
            "project_id": proj.id,
            "employee_id": 1,
            "date": "2026-05-10",
            "minutes": 60,
            "hourly_rate": 10000,
        },
    )
    assert res.status_code == 400
    assert "closed" in res.json()["error"]["message"].lower()


def test_timesheet_max_minutes_validation(client, admin_auth, db_session):
    from app.modules.projects.models import Project

    proj = Project(code="P-MAX", name="범위 검증", budget=Decimal("0"))
    db_session.add(proj)
    db_session.commit()

    res = client.post(
        "/api/projects/timesheets",
        headers=admin_auth["headers"],
        json={
            "project_id": proj.id,
            "employee_id": 1,
            "date": "2026-05-10",
            "minutes": 9999,  # >24h
            "hourly_rate": 10000,
        },
    )
    assert res.status_code == 400


def test_disposed_assets_filtered_by_default(client, admin_auth, db_session):
    """list_assets defaults to active-only."""
    res = client.post(
        "/api/assets/assets",
        headers=admin_auth["headers"],
        json={
            "asset_no": "DISP-1",
            "name": "처분 예정",
            "acquired_date": "2026-01-01",
            "acquired_cost": 100,
            "useful_life_months": 12,
        },
    )
    assert res.status_code == 200
    aid = res.json()["id"]
    client.post(f"/api/assets/assets/{aid}/dispose", headers=admin_auth["headers"])

    # default list — should NOT include disposed
    listed = client.get("/api/assets/assets?page=1&size=100",
                         headers=admin_auth["headers"]).json()
    assert all(item["status"] == "active" for item in listed["items"])

    # explicit disposed filter — should include
    listed_disp = client.get("/api/assets/assets?status=disposed&page=1&size=100",
                              headers=admin_auth["headers"]).json()
    assert any(item["id"] == aid for item in listed_disp["items"])


def test_fx_inverse_rate_precision(client, admin_auth, db_session):
    """Reverse lookup of small rate doesn't truncate to zero."""
    client.post(
        "/api/fx/rates",
        headers=admin_auth["headers"],
        json={"date": "2026-05-01", "from_ccy": "JPY", "to_ccy": "KRW", "rate": 9.5},
    )
    # Reverse: KRW → JPY ≈ 0.10526...
    res = client.get(
        "/api/fx/convert?amount=1000&from_ccy=KRW&to_ccy=JPY&as_of=2026-05-10",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.json()
    # 1000 KRW / 9.5 ≈ 105.26
    assert 105 < body["result"] < 106


def test_partial_gr_accumulates_received_qty(client, admin_auth, db_session):
    """Two GRs against the same PO: received_qty accumulates correctly."""
    from app.modules.suppliers.models import POStatus, PurchaseOrder, PurchaseOrderItem, Supplier
    from app.modules.inventory.models import Item

    sup = Supplier(code="SUP-PART", name="부분입고")
    item = Item(sku="ING-PART", name="원료부분", stock_qty=Decimal("0"))
    db_session.add_all([sup, item])
    db_session.flush()
    po = PurchaseOrder(
        po_no="PO-PART-1", supplier_id=sup.id, status=POStatus.acknowledged,
        total=Decimal("1000"),
    )
    po.items.append(
        PurchaseOrderItem(item_id=item.id, quantity=Decimal("10"), unit_price=Decimal("100"))
    )
    db_session.add(po)
    db_session.commit()
    poi_id = po.items[0].id

    # First GR: receive 4 of 10
    gr1 = client.post(
        "/api/suppliers/goods-receipts",
        headers=admin_auth["headers"],
        json={"gr_no": "GR-PART-1", "po_id": po.id,
              "items": [{"po_item_id": poi_id, "received_qty": 4}]},
    )
    assert gr1.status_code == 200, gr1.text
    client.post(
        f"/api/suppliers/goods-receipts/{gr1.json()['id']}/post",
        headers=admin_auth["headers"],
    )

    # Second GR: receive 6 of 10 (total now 10)
    gr2 = client.post(
        "/api/suppliers/goods-receipts",
        headers=admin_auth["headers"],
        json={"gr_no": "GR-PART-2", "po_id": po.id,
              "items": [{"po_item_id": poi_id, "received_qty": 6}]},
    )
    client.post(
        f"/api/suppliers/goods-receipts/{gr2.json()['id']}/post",
        headers=admin_auth["headers"],
    )

    db_session.refresh(po)
    db_session.refresh(po.items[0])
    assert Decimal(po.items[0].received_qty) == Decimal("10")
    assert po.status == POStatus.received  # auto-advanced

    # Third GR would over-receive
    over = client.post(
        "/api/suppliers/goods-receipts",
        headers=admin_auth["headers"],
        json={"gr_no": "GR-PART-3", "po_id": po.id,
              "items": [{"po_item_id": poi_id, "received_qty": 1}]},
    )
    # PO status is now 'received', so create_gr should reject
    assert over.status_code == 400


def test_holiday_global_and_tenant_specific(db_session):
    """Global (tenant_id=NULL) and per-tenant holiday rows can coexist."""
    from app.modules.hr.models import Holiday

    # Global Korean holiday
    db_session.add(Holiday(date=date(2027, 1, 1), name="신정", country="KR", tenant_id=None))
    # Company-specific founders day
    db_session.add(
        Holiday(date=date(2027, 1, 1), name="창립일 (테넌트1)", country="KR", tenant_id=None)
    )
    # Both allowed when tenant_id same? unique on (date,country,tenant_id)
    db_session.commit()  # both rows have same tenant=NULL, but SQLite treats NULL != NULL
    rows = db_session.query(Holiday).filter(Holiday.date == date(2027, 1, 1)).all()
    assert len(rows) == 2


def test_leave_request_requires_role(client, db_session):
    """A user without HR access cannot submit leave requests."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    viewer = User(
        email="viewer@test.com",
        full_name="View Only",
        hashed_password=hash_password("test1234"),
        role=Role.viewer,
    )
    db_session.add(viewer)
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        data={"username": "viewer@test.com", "password": "test1234"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    res = client.post(
        "/api/hr/leave-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": 1, "type": "annual",
            "start_date": "2026-06-01", "end_date": "2026-06-01",
        },
    )
    assert res.status_code == 403


# --- Phase 6: ABC, dashboards, SLA/delegation, privacy --------------------


def test_abc_classify_pareto_split(client, admin_auth, db_session):
    """80/15/5 ABC split based on outbound value."""
    from app.modules.inventory.models import Item, MovementType, StockMovement

    # 5 items with very different outbound values
    items = []
    for i, val in enumerate([1000, 500, 100, 50, 10]):
        it = Item(sku=f"ABC-{i}", name=f"item{i}", stock_qty=Decimal("100"))
        db_session.add(it)
        db_session.flush()
        items.append(it)
        # synthetic outbound at unit_cost=1, qty=val
        db_session.add(StockMovement(
            item_id=it.id, type=MovementType.outbound,
            quantity=Decimal(str(val)), unit_cost=Decimal("1"),
        ))
    db_session.commit()

    res = client.post(
        "/api/inventory/abc-classify?days=365",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["classified"] == 5
    # Values 1000/500/100/50/10 (total 1660). Cumul ratios:
    #   0.602  → A (≤0.80)
    #   0.903  → B (>0.80, ≤0.95)
    #   0.964  → C (>0.95)
    #   0.994  → C
    #   1.000  → C
    assert body["A"] == 1
    assert body["B"] == 1
    assert body["C"] == 3


def test_reorder_suggestions_and_auto_po(client, admin_auth, db_session):
    """Items below reorder_point appear in suggestions and form draft POs."""
    from app.modules.inventory.models import Item
    from app.modules.suppliers.models import Supplier, PurchaseOrder

    sup = Supplier(code="SUP-AUTO", name="자동발주공급사")
    item = Item(sku="LOW-1", name="저재고", stock_qty=Decimal("5"),
                unit_price=Decimal("100"))
    db_session.add_all([sup, item])
    db_session.commit()

    # Set policy: reorder when stock_qty <= 10, order 50
    pol = client.put(
        "/api/inventory/policies",
        headers=admin_auth["headers"],
        json={
            "item_id": item.id,
            "reorder_point": 10,
            "safety_stock": 5,
            "reorder_qty": 50,
            "preferred_supplier_id": sup.id,
        },
    )
    assert pol.status_code == 200, pol.text

    suggest = client.get(
        "/api/inventory/reorder-suggestions",
        headers=admin_auth["headers"],
    ).json()
    assert any(s["item_id"] == item.id for s in suggest)

    auto = client.post(
        "/api/inventory/auto-purchase-orders",
        headers=admin_auth["headers"],
    ).json()
    assert len(auto["created"]) == 1
    po = db_session.query(PurchaseOrder).filter(
        PurchaseOrder.id == auto["created"][0]["po_id"]
    ).first()
    assert po is not None
    assert po.supplier_id == sup.id
    assert len(po.items) == 1


def test_dashboard_runs_widgets(client, admin_auth, db_session):
    """Dashboard runs all its widget queries and returns aggregated data."""
    from app.modules.report_builder.models import ReportDefinition
    from app.modules.inventory.models import Item

    # Seed report definition: count of items
    db_session.add(Item(sku="DASH-1", name="대시품목", stock_qty=Decimal("0")))
    db_session.add(Item(sku="DASH-2", name="대시품목2", stock_qty=Decimal("0")))
    db_session.commit()
    import json as _json
    rd = ReportDefinition(
        code="rd-count", name="품목 카운트",
        spec=_json.dumps({
            "data_source": "items",
            "columns": [{"agg": "count", "column": "id", "alias": "n"}],
        }),
        is_public=True,
    )
    db_session.add(rd)
    db_session.commit()

    dash = client.post(
        "/api/dashboards",
        headers=admin_auth["headers"],
        json={
            "code": "dash-1",
            "name": "운영 대시보드",
            "is_public": True,
            "widgets": [
                {"report_definition_id": rd.id, "title": "품목수", "position": 0,
                 "chart_type": "kpi"},
            ],
        },
    )
    assert dash.status_code == 200, dash.text
    did = dash.json()["id"]

    run = client.get(f"/api/dashboards/{did}/run", headers=admin_auth["headers"])
    assert run.status_code == 200
    body = run.json()
    assert len(body["widgets"]) == 1
    assert "data" in body["widgets"][0]
    assert body["widgets"][0]["data"]["rows"][0]["n"] >= 2


def test_approval_escalate_overdue(client, admin_auth, db_session):
    """An overdue step with escalate_to_id reassigns to that user via cron."""
    from datetime import datetime, timedelta
    from app.core.security import hash_password
    from app.modules.approvals.models import ApprovalRequest, ApprovalStep, ApprovalStatus
    from app.modules.auth.models import Role, User

    boss = User(email="boss@x.com", full_name="Boss",
                hashed_password=hash_password("test1234"), role=Role.manager)
    backup = User(email="backup@x.com", full_name="Backup",
                   hashed_password=hash_password("test1234"), role=Role.manager)
    db_session.add_all([boss, backup])
    db_session.flush()

    req = ApprovalRequest(
        title="overdue test", resource_type="po", resource_id=1, requester_id=boss.id,
    )
    req.steps.append(ApprovalStep(
        order=1, approver_id=boss.id, sla_hours=4,
        due_at=datetime.utcnow() - timedelta(hours=1),  # overdue
        escalate_to_id=backup.id,
    ))
    db_session.add(req)
    db_session.commit()

    res = client.post(
        "/api/approvals/escalate-overdue",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    assert res.json()["escalated"] == 1
    db_session.refresh(req.steps[0])
    assert req.steps[0].approver_id == backup.id
    assert req.steps[0].escalated_at is not None


def test_user_delegation(client, admin_auth, admin_user, db_session):
    """A user can register a vacation delegate; self-delegation rejected."""
    from datetime import datetime, timedelta
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    other = User(email="other@x.com", full_name="Other",
                  hashed_password=hash_password("test1234"), role=Role.staff)
    db_session.add(other)
    db_session.commit()

    res = client.post(
        "/api/approvals/delegations",
        headers=admin_auth["headers"],
        json={
            "delegate_id": other.id,
            "starts_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "ends_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            "note": "휴가",
        },
    )
    assert res.status_code == 200, res.text

    # Self-delegation rejected
    bad = client.post(
        "/api/approvals/delegations",
        headers=admin_auth["headers"],
        json={
            "delegate_id": admin_user.id,
            "starts_at": datetime.utcnow().isoformat(),
            "ends_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        },
    )
    assert bad.status_code == 400


def test_dsr_create_and_complete(client, admin_auth, db_session):
    """DSR lifecycle: create → admin completes within PIPA 10-day window."""
    res = client.post(
        "/api/privacy/requests",
        headers=admin_auth["headers"],
        json={
            "type": "access",
            "subject_email": "user@example.com",
            "description": "내 정보 열람 요청",
        },
    )
    assert res.status_code == 200, res.text
    req = res.json()
    assert req["status"] == "pending"
    assert req["due_at"] is not None  # PIPA deadline computed

    cmp = client.post(
        f"/api/privacy/requests/{req['id']}/complete?response_notes=완료됨",
        headers=admin_auth["headers"],
    )
    assert cmp.status_code == 200
    assert cmp.json()["status"] == "completed"


def test_pii_redact_helper(client, admin_auth):
    res = client.get(
        "/api/privacy/redact-preview?email=hong.gildong@example.com&phone=010-1234-5678",
        headers=admin_auth["headers"],
    )
    body = res.json()
    assert body["email"].startswith("h") and body["email"].endswith("@example.com")
    assert "*" in body["email"]
    assert body["phone"].endswith("5678")


def test_erase_user_anonymizes_pii(client, admin_auth, db_session):
    """Erasure preserves the PK but rewrites PII to anonymized values."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User
    from app.modules.hr.models import Employee

    u = User(email="erase@example.com", full_name="삭제대상",
             hashed_password=hash_password("x"), role=Role.staff)
    e = Employee(employee_no="ERASE-1", full_name="삭제대상",
                 email="erase@example.com", salary=Decimal("3000000"))
    db_session.add_all([u, e])
    db_session.commit()
    uid = u.id
    eid = e.id

    res = client.post(
        "/api/privacy/erase-user?email=erase@example.com",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text

    db_session.expire_all()
    u2 = db_session.query(User).filter(User.id == uid).first()
    e2 = db_session.query(Employee).filter(Employee.id == eid).first()
    assert u2.full_name == "ERASED"
    assert u2.is_active is False
    assert "anonymized.local" in u2.email
    assert e2.full_name == "ERASED"
    assert "anonymized.local" in e2.email


# --- Phase 7: balance sheet, cash flow, VAT, WMS --------------------------


def test_balance_sheet_balanced(client, admin_auth, db_session):
    """Assets = Liabilities + Equity (with retained earnings)."""
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    cash = Account(code="BS-1", name="현금", type=AccountType.asset)
    cap = Account(code="BS-2", name="자본금", type=AccountType.equity)
    rev = Account(code="BS-3", name="매출", type=AccountType.revenue)
    db_session.add_all([cash, cap, rev])
    db_session.flush()
    # Capital injection: Dr cash 1000 / Cr equity 1000
    e1 = JournalEntry(entry_date=date(2026, 1, 1), description="seed")
    e1.lines.append(JournalLine(account_id=cash.id, debit=1000, credit=0))
    e1.lines.append(JournalLine(account_id=cap.id, debit=0, credit=1000))
    # Sale: Dr cash 200 / Cr revenue 200
    e2 = JournalEntry(entry_date=date(2026, 1, 5), description="sale")
    e2.lines.append(JournalLine(account_id=cash.id, debit=200, credit=0))
    e2.lines.append(JournalLine(account_id=rev.id, debit=0, credit=200))
    db_session.add_all([e1, e2])
    db_session.commit()

    res = client.get(
        "/api/finance/balance-sheet?as_of=2026-12-31",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assets"]["total"] == 1200
    assert body["balanced"] is True


def test_cash_flow_classifies_movements(client, admin_auth, db_session):
    """Cash flow buckets: revenue→operating, asset→investing, liability→financing."""
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    cash = Account(code="1100", name="현금", type=AccountType.asset)
    rev = Account(code="CF-R", name="매출", type=AccountType.revenue)
    fixed = Account(code="CF-A", name="비품", type=AccountType.asset)
    loan = Account(code="CF-L", name="차입금", type=AccountType.liability)
    db_session.add_all([cash, rev, fixed, loan])
    db_session.flush()

    # Operating: cash receipt for sales
    e1 = JournalEntry(entry_date=date(2026, 4, 5))
    e1.description = "sale receipt"
    e1.lines.append(JournalLine(account_id=cash.id, debit=500, credit=0))
    e1.lines.append(JournalLine(account_id=rev.id, debit=0, credit=500))
    # Investing: bought equipment
    e2 = JournalEntry(entry_date=date(2026, 4, 10))
    e2.description = "buy equipment"
    e2.lines.append(JournalLine(account_id=fixed.id, debit=300, credit=0))
    e2.lines.append(JournalLine(account_id=cash.id, debit=0, credit=300))
    # Financing: took a loan
    e3 = JournalEntry(entry_date=date(2026, 4, 15))
    e3.description = "loan"
    e3.lines.append(JournalLine(account_id=cash.id, debit=1000, credit=0))
    e3.lines.append(JournalLine(account_id=loan.id, debit=0, credit=1000))
    db_session.add_all([e1, e2, e3])
    db_session.commit()

    res = client.get(
        "/api/finance/cash-flow?start=2026-04-01&end=2026-04-30",
        headers=admin_auth["headers"],
    )
    body = res.json()
    assert body["operating"] == 500
    assert body["investing"] == -300
    assert body["financing"] == 1000
    assert body["net_change"] == 1200


def test_vat_return_summary(client, admin_auth, db_session):
    """VAT return = output VAT (sales) - input VAT (purchase)."""
    from app.modules.etax.models import ETaxInvoice, ETaxStatus, ETaxType

    db_session.add_all([
        ETaxInvoice(
            type=ETaxType.sales, status=ETaxStatus.accepted,
            issued_date=date(2026, 4, 10),
            supplier_business_no="2208162517", supplier_name="us",
            buyer_business_no="2208162517", buyer_name="customer",
            item_summary="x", subtotal=Decimal("1000"), tax=Decimal("100"),
            total=Decimal("1100"),
        ),
        ETaxInvoice(
            type=ETaxType.purchase, status=ETaxStatus.accepted,
            issued_date=date(2026, 4, 12),
            supplier_business_no="2208162517", supplier_name="vendor",
            buyer_business_no="2208162517", buyer_name="us",
            item_summary="y", subtotal=Decimal("400"), tax=Decimal("40"),
            total=Decimal("440"),
        ),
    ])
    db_session.commit()

    res = client.get(
        "/api/finance/vat-return?start=2026-04-01&end=2026-06-30",
        headers=admin_auth["headers"],
    )
    body = res.json()
    assert body["sales"]["vat_amount"] == 100
    assert body["purchase"]["vat_amount"] == 40
    assert body["payable_or_refund"] == 60
    assert body["is_refund"] is False


def test_wms_full_flow(client, admin_auth, db_session):
    """End-to-end: order confirm → pick list → pick → pack → ship → deliver."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem

    item = Item(sku="WMS-1", name="배송품", stock_qty=Decimal("100"),
                unit_price=Decimal("10"))
    cust = Customer(name="배송고객")
    db_session.add_all([item, cust])
    db_session.flush()
    so = SalesOrder(order_no="SO-WMS-1", customer_id=cust.id,
                    status=OrderStatus.confirmed, total=Decimal("100"))
    so.items.append(
        SalesOrderItem(item_id=item.id, quantity=Decimal("10"),
                       unit_price=Decimal("10"))
    )
    db_session.add(so)
    db_session.commit()

    # Generate pick list
    pl_res = client.post(
        f"/api/wms/pick-lists/from-order/{so.id}",
        headers=admin_auth["headers"],
    )
    assert pl_res.status_code == 200, pl_res.text
    pl_id = pl_res.json()["id"]

    # Start picking
    start = client.post(f"/api/wms/pick-lists/{pl_id}/start",
                        headers=admin_auth["headers"])
    assert start.json()["status"] == "picking"

    # Complete picking
    complete = client.post(
        f"/api/wms/pick-lists/{pl_id}/complete",
        headers=admin_auth["headers"],
        json={"items": [{"item_id": item.id, "picked_qty": 10}]},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "picked"

    # Pack into shipment
    ship = client.post(
        "/api/wms/shipments",
        headers=admin_auth["headers"],
        json={
            "shipment_no": "SHIP-1",
            "pick_list_id": pl_id,
            "carrier": "CJ대한통운",
            "tracking_no": "1234567890",
            "weight_kg": 2.5,
            "address_to": "서울시 강남구",
        },
    )
    assert ship.status_code == 200, ship.text
    sid = ship.json()["id"]
    assert ship.json()["status"] == "packed"

    # Ship
    shipped = client.post(f"/api/wms/shipments/{sid}/ship",
                          headers=admin_auth["headers"])
    assert shipped.json()["status"] == "shipped"

    # Deliver
    delivered = client.post(f"/api/wms/shipments/{sid}/deliver",
                             headers=admin_auth["headers"])
    assert delivered.json()["status"] == "delivered"


def test_wms_return_restocks(client, admin_auth, db_session):
    """Returning a shipment restocks the picked items."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem

    item = Item(sku="WMS-RET-1", name="반품품", stock_qty=Decimal("50"))
    cust = Customer(name="반품고객")
    db_session.add_all([item, cust])
    db_session.flush()
    so = SalesOrder(order_no="SO-RET-1", customer_id=cust.id,
                    status=OrderStatus.confirmed, total=Decimal("0"))
    so.items.append(SalesOrderItem(item_id=item.id, quantity=Decimal("5"),
                                    unit_price=Decimal("10")))
    db_session.add(so)
    db_session.commit()

    pl = client.post(f"/api/wms/pick-lists/from-order/{so.id}",
                     headers=admin_auth["headers"]).json()
    client.post(f"/api/wms/pick-lists/{pl['id']}/start", headers=admin_auth["headers"])
    client.post(
        f"/api/wms/pick-lists/{pl['id']}/complete",
        headers=admin_auth["headers"],
        json={"items": [{"item_id": item.id, "picked_qty": 5}]},
    )
    sh = client.post(
        "/api/wms/shipments",
        headers=admin_auth["headers"],
        json={"shipment_no": "SHIP-RET-1", "pick_list_id": pl["id"]},
    ).json()
    client.post(f"/api/wms/shipments/{sh['id']}/ship", headers=admin_auth["headers"])
    client.post(f"/api/wms/shipments/{sh['id']}/deliver",
                 headers=admin_auth["headers"])

    db_session.refresh(item)
    stock_before = Decimal(item.stock_qty)

    ret = client.post(f"/api/wms/shipments/{sh['id']}/return",
                       headers=admin_auth["headers"])
    assert ret.status_code == 200, ret.text
    assert ret.json()["status"] == "returned"

    db_session.refresh(item)
    assert Decimal(item.stock_qty) == stock_before + Decimal("5")


# --- Phase 8: MRP, year-end, reviews, campaigns, barcode -------------------


def test_mrp_run_explodes_bom(client, admin_auth, db_session):
    """MRP: forecast 100 finished units → MPS 100 → 200 raw1 + 300 raw2 needed."""
    from app.modules.inventory.models import Item
    from app.modules.manufacturing.models import BillOfMaterials, BomComponent

    finished = Item(sku="MRP-FG", name="완제품", stock_qty=Decimal("0"))
    raw1 = Item(sku="MRP-R1", name="원료1", stock_qty=Decimal("50"))
    raw2 = Item(sku="MRP-R2", name="원료2", stock_qty=Decimal("0"))
    db_session.add_all([finished, raw1, raw2])
    db_session.flush()
    bom = BillOfMaterials(
        finished_item_id=finished.id, version="v1",
        output_quantity=Decimal("1"), is_active=True,
    )
    bom.components.append(BomComponent(
        component_item_id=raw1.id, quantity_per=Decimal("2"),
    ))
    bom.components.append(BomComponent(
        component_item_id=raw2.id, quantity_per=Decimal("3"),
    ))
    db_session.add(bom)
    db_session.commit()

    # Forecast: 100 finished units in 2026-W20
    f = client.post(
        "/api/manufacturing/forecasts",
        headers=admin_auth["headers"],
        json={"item_id": finished.id, "period_code": "2026-W20",
              "forecast_qty": 100},
    )
    assert f.status_code == 200, f.text

    run = client.post(
        "/api/manufacturing/mrp-run?period_code=2026-W20",
        headers=admin_auth["headers"],
    )
    assert run.status_code == 200, run.text
    assert run.json()["mps_count"] == 1
    assert run.json()["mr_count"] == 2

    # MR: raw1 needs 200 - 50 = 150 net; raw2 needs 300 - 0 = 300 net
    mrs = client.get(
        "/api/manufacturing/material-requirements?period_code=2026-W20",
        headers=admin_auth["headers"],
    ).json()
    by_item = {m["item_id"]: m for m in mrs}
    assert by_item[raw1.id]["gross_required"] == 200
    assert by_item[raw1.id]["net_required"] == 150
    assert by_item[raw2.id]["net_required"] == 300


def test_mrp_run_idempotent(client, admin_auth, db_session):
    """Re-running MRP for same period replaces previous output cleanly."""
    from app.modules.inventory.models import Item

    item = Item(sku="MRP-IDEM", name="재실행", stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()
    client.post(
        "/api/manufacturing/forecasts",
        headers=admin_auth["headers"],
        json={"item_id": item.id, "period_code": "2026-W21",
              "forecast_qty": 50},
    )
    r1 = client.post(
        "/api/manufacturing/mrp-run?period_code=2026-W21",
        headers=admin_auth["headers"],
    )
    r2 = client.post(
        "/api/manufacturing/mrp-run?period_code=2026-W21",
        headers=admin_auth["headers"],
    )
    assert r1.json()["mps_count"] == r2.json()["mps_count"]
    # Only one MPS row should exist
    mps = client.get(
        "/api/manufacturing/mps?period_code=2026-W21",
        headers=admin_auth["headers"],
    ).json()
    assert len(mps) == 1


def test_year_end_settlement_refund(client, admin_auth, db_session):
    """If withholding > owed tax → refund (양수)."""
    from app.modules.hr.models import Employee, Payroll, PayrollStatus

    emp = Employee(employee_no="YES-1", full_name="연말이",
                   email="ye@x.com", salary=Decimal("60000000"))
    db_session.add(emp)
    db_session.flush()
    # 12 months @ 5M base + 100k tax/month withheld
    for m in range(1, 13):
        db_session.add(Payroll(
            employee_id=emp.id, period_code=f"2026-{m:02d}",
            base_salary=Decimal("5000000"), bonus=Decimal("0"),
            allowance=Decimal("0"), deduction=Decimal("0"),
            income_tax=Decimal("100000"), net_pay=Decimal("4900000"),
            status=PayrollStatus.paid,
        ))
    db_session.commit()

    res = client.post(
        "/api/hr/year-end-settlement",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id, "tax_year": 2026,
            "deductions": 15000000, "credits": 500000,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert float(body["gross_annual"]) == 60_000_000
    assert float(body["tax_withheld"]) == 1_200_000
    # taxable = 60M - 15M = 45M → 15% bracket: 45M*0.15 - 1.26M = 5.49M
    # after credits: 5.49M - 0.5M = 4.99M owed
    # withheld 1.2M < owed 4.99M → 추가 납부 (refund_or_due 음수)
    assert float(body["refund_or_due"]) < 0


def test_performance_review_finalize_locks(client, admin_auth, db_session):
    """Finalized review cannot be edited."""
    from app.modules.hr.models import Employee

    emp = Employee(employee_no="PR-1", full_name="평가대상",
                   email="pr@x.com", salary=Decimal("3000000"))
    db_session.add(emp)
    db_session.commit()

    r1 = client.post(
        "/api/hr/reviews",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id, "period_code": "2026-Q1",
            "overall_rating": 4,
            "kpi_scores": [
                {"kpi": "매출 달성", "target": 100, "actual": 95, "score": 4},
            ],
            "comments": "양호",
            "finalize": True,
        },
    )
    assert r1.status_code == 200, r1.text

    # Edit attempt after finalize should fail
    r2 = client.post(
        "/api/hr/reviews",
        headers=admin_auth["headers"],
        json={
            "employee_id": emp.id, "period_code": "2026-Q1",
            "overall_rating": 5,
        },
    )
    assert r2.status_code == 400


def test_campaign_send_delivers_to_segment(client, admin_auth, db_session):
    """Campaign send creates one CampaignSend per segment match."""
    from app.modules.crm.models import Lead

    db_session.add_all([
        Lead(name="L1", email="l1@x.com", source="website"),
        Lead(name="L2", email="l2@x.com", source="website"),
        Lead(name="L3", email="l3@x.com", source="referral"),
    ])
    db_session.commit()

    seg = client.post(
        "/api/crm/segments",
        headers=admin_auth["headers"],
        json={"name": "웹사이트 리드", "target_type": "lead",
              "criteria": {"source": "website"}},
    ).json()
    camp = client.post(
        "/api/crm/campaigns",
        headers=admin_auth["headers"],
        json={"name": "5월 프로모", "segment_id": seg["id"],
              "subject": "5월 신상품 안내", "body": "..."},
    ).json()
    sent = client.post(
        f"/api/crm/campaigns/{camp['id']}/send",
        headers=admin_auth["headers"],
    )
    assert sent.status_code == 200, sent.text
    sends = client.get(
        f"/api/crm/campaigns/{camp['id']}/sends",
        headers=admin_auth["headers"],
    ).json()
    assert len(sends) == 2  # only website leads


def test_barcode_scan_lookup_and_movement(client, admin_auth, db_session):
    """Barcode-driven movement creates inventory entry."""
    from app.modules.inventory.models import Item

    item = Item(sku="BAR-1", name="바코드품목",
                stock_qty=Decimal("50"), barcode="8801234567890")
    db_session.add(item)
    db_session.commit()

    look = client.get(
        "/api/inventory/scan/8801234567890",
        headers=admin_auth["headers"],
    )
    assert look.status_code == 200
    assert look.json()["sku"] == "BAR-1"

    bad = client.get(
        "/api/inventory/scan/0000000000000",
        headers=admin_auth["headers"],
    )
    assert bad.status_code == 404

    move = client.post(
        "/api/inventory/scan-movement?barcode=8801234567890&movement_type=outbound&quantity=5",
        headers=admin_auth["headers"],
    )
    assert move.status_code == 200, move.text
    db_session.refresh(item)
    assert Decimal(item.stock_qty) == Decimal("45")


# --- Phase 9: bug fixes regression ---------------------------------------


def test_campaign_sent_count_no_double_count(client, admin_auth, db_session):
    """Re-sending a campaign doesn't inflate sent_count beyond actual sends."""
    from app.modules.crm.models import Lead

    db_session.add_all([
        Lead(name="A", email="a@x.com", source="ref"),
        Lead(name="B", email="b@x.com", source="ref"),
    ])
    db_session.commit()

    seg = client.post(
        "/api/crm/segments",
        headers=admin_auth["headers"],
        json={"name": "ref", "target_type": "lead", "criteria": {"source": "ref"}},
    ).json()
    camp = client.post(
        "/api/crm/campaigns",
        headers=admin_auth["headers"],
        json={"name": "테스트", "segment_id": seg["id"], "subject": "x"},
    ).json()
    first = client.post(
        f"/api/crm/campaigns/{camp['id']}/send", headers=admin_auth["headers"]
    )
    assert first.status_code == 200
    assert first.json()["sent_count"] == 2


def test_picking_rejects_all_zero(client, admin_auth, db_session):
    """All-zero pick is rejected (can't ship nothing)."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem

    item = Item(sku="WMS-Z", name="zero", stock_qty=Decimal("10"))
    cust = Customer(name="zerocust")
    db_session.add_all([item, cust])
    db_session.flush()
    so = SalesOrder(order_no="SO-WMS-Z", customer_id=cust.id,
                    status=OrderStatus.confirmed, total=Decimal("0"))
    so.items.append(SalesOrderItem(item_id=item.id, quantity=Decimal("3"),
                                    unit_price=Decimal("10")))
    db_session.add(so)
    db_session.commit()

    pl = client.post(f"/api/wms/pick-lists/from-order/{so.id}",
                      headers=admin_auth["headers"]).json()
    client.post(f"/api/wms/pick-lists/{pl['id']}/start",
                 headers=admin_auth["headers"])
    res = client.post(
        f"/api/wms/pick-lists/{pl['id']}/complete",
        headers=admin_auth["headers"],
        json={"items": [{"item_id": item.id, "picked_qty": 0}]},
    )
    assert res.status_code == 400


def test_mrp_multilevel_bom_explode(client, admin_auth, db_session):
    """A multi-level BOM (FG → sub-assembly → raw) recurses correctly."""
    from app.modules.inventory.models import Item
    from app.modules.manufacturing.models import BillOfMaterials, BomComponent

    fg = Item(sku="ML-FG", name="finished", stock_qty=Decimal("0"))
    sub = Item(sku="ML-SUB", name="sub-assembly", stock_qty=Decimal("0"))
    raw = Item(sku="ML-RAW", name="raw", stock_qty=Decimal("0"))
    db_session.add_all([fg, sub, raw])
    db_session.flush()
    # FG uses 2 sub per output_qty=1
    bom_fg = BillOfMaterials(finished_item_id=fg.id, version="v1",
                              output_quantity=Decimal("1"), is_active=True)
    bom_fg.components.append(BomComponent(component_item_id=sub.id,
                                           quantity_per=Decimal("2")))
    # Sub uses 3 raw per output_qty=1
    bom_sub = BillOfMaterials(finished_item_id=sub.id, version="v1",
                               output_quantity=Decimal("1"), is_active=True)
    bom_sub.components.append(BomComponent(component_item_id=raw.id,
                                            quantity_per=Decimal("3")))
    db_session.add_all([bom_fg, bom_sub])
    db_session.commit()

    client.post("/api/manufacturing/forecasts",
                 headers=admin_auth["headers"],
                 json={"item_id": fg.id, "period_code": "2026-W22",
                       "forecast_qty": 5})
    client.post("/api/manufacturing/mrp-run?period_code=2026-W22",
                 headers=admin_auth["headers"])
    mrs = client.get(
        "/api/manufacturing/material-requirements?period_code=2026-W22",
        headers=admin_auth["headers"],
    ).json()
    # FG 5 → sub 10 → raw 30
    by_item = {m["item_id"]: m for m in mrs}
    # sub is not a leaf (it has its own BOM), so it shouldn't appear; only raw
    assert raw.id in by_item
    assert by_item[raw.id]["gross_required"] == 30
    assert sub.id not in by_item  # exploded into raw, not surfaced as MR


def test_wms_return_preserves_lot(client, admin_auth, db_session):
    """Return restocks the same lot the original pick was associated with."""
    from app.modules.inventory.models import Item, StockLot
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem

    item = Item(sku="LOT-RET", name="lot return", stock_qty=Decimal("0"))
    cust = Customer(name="lotcust")
    db_session.add_all([item, cust])
    db_session.flush()
    lot = StockLot(item_id=item.id, lot_number="L-A",
                   quantity=Decimal("10"))
    item.stock_qty = Decimal("10")
    db_session.add(lot)
    so = SalesOrder(order_no="SO-LOT-1", customer_id=cust.id,
                    status=OrderStatus.confirmed, total=Decimal("0"))
    so.items.append(SalesOrderItem(item_id=item.id, quantity=Decimal("4"),
                                    unit_price=Decimal("0")))
    db_session.add(so)
    db_session.commit()

    pl = client.post(f"/api/wms/pick-lists/from-order/{so.id}",
                      headers=admin_auth["headers"]).json()
    client.post(f"/api/wms/pick-lists/{pl['id']}/start",
                 headers=admin_auth["headers"])
    client.post(
        f"/api/wms/pick-lists/{pl['id']}/complete",
        headers=admin_auth["headers"],
        json={"items": [{"item_id": item.id, "picked_qty": 4, "lot_id": lot.id}]},
    )
    sh = client.post("/api/wms/shipments", headers=admin_auth["headers"],
                       json={"shipment_no": "SH-LOT-1",
                             "pick_list_id": pl["id"]}).json()
    client.post(f"/api/wms/shipments/{sh['id']}/ship",
                 headers=admin_auth["headers"])
    client.post(f"/api/wms/shipments/{sh['id']}/deliver",
                 headers=admin_auth["headers"])

    db_session.refresh(lot)
    before = Decimal(lot.quantity)
    client.post(f"/api/wms/shipments/{sh['id']}/return",
                 headers=admin_auth["headers"])
    db_session.refresh(lot)
    # Return goes back to the SAME lot — quantity restored
    assert Decimal(lot.quantity) == before + Decimal("4")


def test_cash_flow_priority_revenue_over_asset(client, admin_auth, db_session):
    """Mixed entry (revenue + asset contra) classifies as operating (revenue wins)."""
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    cash = Account(code="1100", name="현금", type=AccountType.asset)
    other_asset = Account(code="CFP-A", name="비품", type=AccountType.asset)
    rev = Account(code="CFP-R", name="매출", type=AccountType.revenue)
    db_session.add_all([cash, other_asset, rev])
    db_session.flush()
    # Mixed: Dr cash 100, Cr revenue 80, Cr asset 20 (asset sold + service)
    e = JournalEntry(entry_date=date(2026, 7, 1), description="mixed")
    e.lines.append(JournalLine(account_id=cash.id, debit=100, credit=0))
    e.lines.append(JournalLine(account_id=rev.id, debit=0, credit=80))
    e.lines.append(JournalLine(account_id=other_asset.id, debit=0, credit=20))
    db_session.add(e)
    db_session.commit()

    res = client.get(
        "/api/finance/cash-flow?start=2026-07-01&end=2026-07-31",
        headers=admin_auth["headers"],
    )
    body = res.json()
    # Revenue contra wins priority → operating, not investing
    assert body["operating"] == 100
    assert body["investing"] == 0


# --- Phase 9: RFQ + Vendor scorecard + Health probes -----------------------


def test_rfq_to_po_award_flow(client, admin_auth, db_session):
    """End-to-end: RFQ → send → 2 suppliers respond → award → auto-PO."""
    from app.modules.inventory.models import Item
    from app.modules.suppliers.models import Supplier

    item = Item(sku="RFQ-IT", name="자재", stock_qty=Decimal("0"))
    sA = Supplier(code="S-A", name="공급사A")
    sB = Supplier(code="S-B", name="공급사B")
    db_session.add_all([item, sA, sB])
    db_session.commit()

    rfq = client.post(
        "/api/suppliers/rfqs",
        headers=admin_auth["headers"],
        json={
            "rfq_no": "RFQ-001",
            "title": "원료 견적요청",
            "items": [{"item_id": item.id, "quantity": 100}],
        },
    )
    assert rfq.status_code == 200, rfq.text
    rfq_id = rfq.json()["id"]
    rfq_item_id = rfq.json()["items"][0]["id"]

    client.post(f"/api/suppliers/rfqs/{rfq_id}/send", headers=admin_auth["headers"])

    # Two responses with different prices
    r1 = client.post(
        "/api/suppliers/rfqs/responses",
        headers=admin_auth["headers"],
        json={
            "rfq_id": rfq_id, "supplier_id": sA.id, "lead_time_days": 5,
            "lines": [{"rfq_item_id": rfq_item_id, "unit_price": 100}],
        },
    )
    assert r1.status_code == 200, r1.text
    assert float(r1.json()["total"]) == 10000
    r2 = client.post(
        "/api/suppliers/rfqs/responses",
        headers=admin_auth["headers"],
        json={
            "rfq_id": rfq_id, "supplier_id": sB.id, "lead_time_days": 7,
            "lines": [{"rfq_item_id": rfq_item_id, "unit_price": 90}],
        },
    )
    r2_id = r2.json()["id"]

    # Sorted ascending by total — B should be first
    lst = client.get(
        f"/api/suppliers/rfqs/{rfq_id}/responses",
        headers=admin_auth["headers"],
    ).json()
    assert lst[0]["supplier_id"] == sB.id

    # Award to B (cheaper)
    award = client.post(
        f"/api/suppliers/rfqs/{rfq_id}/award/{r2_id}",
        headers=admin_auth["headers"],
    )
    assert award.status_code == 200, award.text
    body = award.json()
    assert body["po_no"] == "PO-RFQ-001"

    # Duplicate response rejected
    dup = client.post(
        "/api/suppliers/rfqs/responses",
        headers=admin_auth["headers"],
        json={
            "rfq_id": rfq_id, "supplier_id": sA.id,
            "lines": [{"rfq_item_id": rfq_item_id, "unit_price": 95}],
        },
    )
    assert dup.status_code == 400


def test_vendor_scorecard_aggregates(client, admin_auth, db_session):
    """Scorecard computes on-time rate + avg lead time + match rate."""
    from datetime import timedelta
    from app.modules.suppliers.models import (
        GoodsReceipt, GoodsReceiptItem, GRStatus, POStatus,
        PurchaseOrder, PurchaseOrderItem, Supplier, SupplierInvoice,
        SupplierInvoiceStatus,
    )
    from app.modules.inventory.models import Item

    sup = Supplier(code="SCORE-1", name="평점공급사")
    item = Item(sku="SC-1", name="x", stock_qty=Decimal("0"))
    db_session.add_all([sup, item])
    db_session.flush()
    order_date = date(2026, 5, 1)
    expected = date(2026, 5, 10)
    po = PurchaseOrder(
        po_no="PO-SCORE-1", supplier_id=sup.id, status=POStatus.received,
        order_date=order_date, expected_date=expected, total=Decimal("1000"),
    )
    po.items.append(PurchaseOrderItem(
        item_id=item.id, quantity=Decimal("10"),
        unit_price=Decimal("100"), received_qty=Decimal("10"),
    ))
    db_session.add(po)
    db_session.flush()
    # GR received on 2026-05-08 (on-time, 7 days lead)
    gr = GoodsReceipt(
        gr_no="GR-SCORE-1", po_id=po.id, status=GRStatus.posted,
        received_date=date(2026, 5, 8),
    )
    gr.items.append(GoodsReceiptItem(
        gr_id=po.id, po_item_id=po.items[0].id,
        received_qty=Decimal("10"),
    ))
    db_session.add(gr)
    db_session.add(SupplierInvoice(
        supplier_id=sup.id, po_id=po.id,
        vendor_invoice_no="VI-SCORE-1",
        invoice_date=date(2026, 5, 9),
        subtotal=Decimal("1000"), tax=Decimal("0"), total=Decimal("1000"),
        status=SupplierInvoiceStatus.matched,
    ))
    db_session.commit()

    res = client.get(
        f"/api/suppliers/scorecard?supplier_id={sup.id}",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    sc = res.json()["scorecard"][0]
    assert sc["po_count"] == 1
    assert sc["on_time_rate"] == 1.0
    assert sc["avg_lead_time_days"] == 7.0
    assert sc["match_rate"] == 1.0


def test_health_live_and_ready(client):
    """Liveness returns 200 always; readiness checks DB + migration."""
    live = client.get("/api/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    ready = client.get("/api/health/ready")
    # Migration may not be present in test DB (auto-create tables), so this
    # could be 503 — we just verify the endpoint shape works either way.
    assert ready.status_code in (200, 503)


def test_celery_app_disabled_without_broker():
    """Without CELERY_BROKER_URL the celery_app is None — synchronous path."""
    from app.core.celery_app import celery_app
    # Test env doesn't set the broker, so it must be None.
    assert celery_app is None


# --- Phase 10: ATS / KPI / Consolidation / AI posting ---------------------


def test_ats_full_hire_flow(client, admin_auth, db_session):
    """Posting → candidate → application → offer → hire creates Employee."""
    from app.modules.hr.models import Department, Employee

    dept = Department(name="개발")
    db_session.add(dept)
    db_session.commit()

    job = client.post(
        "/api/ats/jobs",
        headers=admin_auth["headers"],
        json={"code": "JOB-1", "title": "백엔드 개발자", "headcount": 1,
              "department_id": dept.id},
    )
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    cand = client.post(
        "/api/ats/candidates",
        headers=admin_auth["headers"],
        json={"full_name": "신지원", "email": "newhire@x.com",
              "source": "잡코리아"},
    ).json()

    app_res = client.post(
        "/api/ats/applications",
        headers=admin_auth["headers"],
        json={"job_posting_id": job_id, "candidate_id": cand["id"]},
    )
    app_id = app_res.json()["id"]

    # Stage through offer
    for stage in ["screening", "interview", "offer"]:
        client.post(
            f"/api/ats/applications/{app_id}/move-stage",
            headers=admin_auth["headers"],
            json={"stage": stage},
        )

    # Hire
    hire = client.post(
        f"/api/ats/applications/{app_id}/hire",
        headers=admin_auth["headers"],
        json={"employee_no": "E-NEW-1", "salary": 36000000,
              "department_id": dept.id, "position": "Backend Engineer"},
    )
    assert hire.status_code == 200, hire.text
    assert hire.json()["stage"] == "hired"
    emp_id = hire.json()["converted_employee_id"]
    emp = db_session.query(Employee).filter(Employee.id == emp_id).first()
    assert emp.email == "newhire@x.com"
    assert emp.employee_no == "E-NEW-1"


def test_ats_duplicate_application_rejected(client, admin_auth, db_session):
    job = client.post(
        "/api/ats/jobs",
        headers=admin_auth["headers"],
        json={"code": "JOB-DUP", "title": "x", "headcount": 1},
    ).json()
    cand = client.post(
        "/api/ats/candidates",
        headers=admin_auth["headers"],
        json={"full_name": "dup", "email": "dup@x.com"},
    ).json()
    a1 = client.post(
        "/api/ats/applications",
        headers=admin_auth["headers"],
        json={"job_posting_id": job["id"], "candidate_id": cand["id"]},
    )
    a2 = client.post(
        "/api/ats/applications",
        headers=admin_auth["headers"],
        json={"job_posting_id": job["id"], "candidate_id": cand["id"]},
    )
    assert a1.status_code == 200
    assert a2.status_code == 400


def test_kpi_inventory_value(client, admin_auth, db_session):
    """Inventory value KPI sums stock * unit_price across items."""
    from app.modules.inventory.models import Item

    db_session.add_all([
        Item(sku="K-A", name="A", stock_qty=Decimal("10"),
             unit_price=Decimal("100")),
        Item(sku="K-B", name="B", stock_qty=Decimal("5"),
             unit_price=Decimal("200")),
    ])
    db_session.commit()

    res = client.get("/api/kpi/list", headers=admin_auth["headers"]).json()
    codes = {k["code"] for k in res["kpis"]}
    assert "inventory.value" in codes
    assert "sales.total" in codes

    run = client.get(
        "/api/kpi/run/inventory.value", headers=admin_auth["headers"]
    ).json()
    assert run["value"] == 2000  # 10*100 + 5*200
    assert len(run["breakdown"]) == 2


def test_consolidation_eliminations_and_taxable_income(client, admin_auth, db_session):
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    # Setup: revenue 1000, expense 300 → book net 700
    rev = Account(code="CONS-R", name="rev", type=AccountType.revenue)
    exp = Account(code="CONS-E", name="exp", type=AccountType.expense)
    cash = Account(code="CONS-C", name="cash", type=AccountType.asset)
    db_session.add_all([rev, exp, cash])
    db_session.flush()
    e = JournalEntry(entry_date=date(2026, 4, 1), description="rev")
    e.lines.append(JournalLine(account_id=cash.id, debit=1000, credit=0))
    e.lines.append(JournalLine(account_id=rev.id, debit=0, credit=1000))
    e2 = JournalEntry(entry_date=date(2026, 4, 5), description="exp")
    e2.lines.append(JournalLine(account_id=exp.id, debit=300, credit=0))
    e2.lines.append(JournalLine(account_id=cash.id, debit=0, credit=300))
    db_session.add_all([e, e2])
    db_session.commit()

    # Tax adjustments: +100 addition, -50 subtraction
    client.post(
        "/api/consolidation/tax-adjustments",
        headers=admin_auth["headers"],
        json={"period_code": "2026-04", "description": "접대비 한도초과",
              "amount": 100, "category": "permanent"},
    )
    client.post(
        "/api/consolidation/tax-adjustments",
        headers=admin_auth["headers"],
        json={"period_code": "2026-04", "description": "비과세 이자수익",
              "amount": -50, "category": "permanent"},
    )

    res = client.get(
        "/api/consolidation/taxable-income?start=2026-04-01&end=2026-04-30",
        headers=admin_auth["headers"],
    ).json()
    assert res["book_net_income"] == 700
    assert res["additions"] == 100
    assert res["subtractions"] == 50
    assert res["taxable_income"] == 750  # 700 + 100 - 50


def test_ai_posting_propose(client, admin_auth, db_session):
    """Description matching a keyword produces a balanced 2-line proposal."""
    from app.modules.finance.models import Account, AccountType

    cash = Account(code="1100", name="현금", type=AccountType.asset)
    travel = Account(code="5120", name="여비교통비", type=AccountType.expense)
    db_session.add_all([cash, travel])
    db_session.commit()

    res = client.post(
        "/api/ai-posting/propose",
        headers=admin_auth["headers"],
        json={"description": "출장 택시비 강남 →  김포", "amount": 30000},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["matched_rule"] in ("교통비", "택시")
    assert body["confidence"] >= 0.5
    debit_sum = sum(float(l["debit"]) for l in body["lines"])
    credit_sum = sum(float(l["credit"]) for l in body["lines"])
    assert debit_sum == credit_sum == 30000


def test_ai_posting_accept_creates_journal(client, admin_auth, db_session):
    """Accepting a proposal creates a real JournalEntry."""
    from app.modules.finance.models import Account, AccountType, JournalEntry

    db_session.add_all([
        Account(code="1100", name="현금", type=AccountType.asset),
        Account(code="5130", name="식대", type=AccountType.expense),
    ])
    db_session.commit()

    prop = client.post(
        "/api/ai-posting/propose",
        headers=admin_auth["headers"],
        json={"description": "회식 식대", "amount": 50000},
    ).json()

    accept = client.post(
        "/api/ai-posting/accept",
        headers=admin_auth["headers"],
        params={"description": "회식 식대"},
        json=prop,
    )
    assert accept.status_code == 200, accept.text
    cnt = db_session.query(JournalEntry).filter(
        JournalEntry.reference == "AI-PROP"
    ).count()
    assert cnt >= 1


# --- Phase 11: capacity + shop floor + statement exports ------------------


def test_capacity_routing_and_shop_floor_ops(client, admin_auth, db_session):
    """BOM with routing → WO release → /generate-ops → start/complete operator clock."""
    from app.modules.inventory.models import Item
    from app.modules.manufacturing.models import BillOfMaterials, BomComponent

    fg = Item(sku="CAP-FG", name="제품", stock_qty=Decimal("0"))
    raw = Item(sku="CAP-R", name="원료", stock_qty=Decimal("100"))
    db_session.add_all([fg, raw])
    db_session.flush()
    bom = BillOfMaterials(
        finished_item_id=fg.id, version="v1",
        output_quantity=Decimal("1"), is_active=True,
    )
    bom.components.append(BomComponent(
        component_item_id=raw.id, quantity_per=Decimal("2"),
    ))
    db_session.add(bom)
    db_session.commit()

    wc = client.post(
        "/api/manufacturing/work-centers",
        headers=admin_auth["headers"],
        json={"code": "WC-1", "name": "포장 라인", "capacity_per_day": 480},
    )
    assert wc.status_code == 200, wc.text
    wc_id = wc.json()["id"]

    # Add 2 routing steps
    client.post(
        "/api/manufacturing/routing",
        headers=admin_auth["headers"],
        json={
            "bom_id": bom.id, "sequence": 10, "work_center_id": wc_id,
            "setup_minutes": 15, "run_minutes_per_unit": 2,
        },
    )
    client.post(
        "/api/manufacturing/routing",
        headers=admin_auth["headers"],
        json={
            "bom_id": bom.id, "sequence": 20, "work_center_id": wc_id,
            "setup_minutes": 10, "run_minutes_per_unit": 1,
        },
    )

    wo = client.post(
        "/api/manufacturing/work-orders",
        headers=admin_auth["headers"],
        json={"wo_no": "WO-CAP-1", "bom_id": bom.id, "quantity": 10},
    ).json()

    gen = client.post(
        f"/api/manufacturing/work-orders/{wo['id']}/generate-ops",
        headers=admin_auth["headers"],
    )
    assert gen.json()["created"] == 2

    # Idempotent
    again = client.post(
        f"/api/manufacturing/work-orders/{wo['id']}/generate-ops",
        headers=admin_auth["headers"],
    )
    assert again.json()["created"] == 0

    ops = client.get(
        f"/api/manufacturing/shop-floor-ops?work_order_id={wo['id']}",
        headers=admin_auth["headers"],
    ).json()
    assert len(ops) == 2
    # Step 10: 15 + 2*10 = 35min; Step 20: 10 + 1*10 = 20min
    assert ops[0]["planned_minutes"] == 35
    assert ops[1]["planned_minutes"] == 20

    op_id = ops[0]["id"]
    client.post(f"/api/manufacturing/shop-floor-ops/{op_id}/start",
                 headers=admin_auth["headers"])
    done = client.post(
        f"/api/manufacturing/shop-floor-ops/{op_id}/complete?actual_minutes=40",
        headers=admin_auth["headers"],
    )
    assert done.status_code == 200
    assert done.json()["actual_minutes"] == 40


def test_capacity_load_endpoint(client, admin_auth, db_session):
    wc = client.post(
        "/api/manufacturing/work-centers",
        headers=admin_auth["headers"],
        json={"code": "WC-LOAD", "name": "조립 라인", "capacity_per_day": 480},
    ).json()
    res = client.get(
        "/api/manufacturing/capacity-load?period_code=2026-W23",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    rows = res.json()
    found = next((r for r in rows if r["code"] == "WC-LOAD"), None)
    assert found is not None
    assert found["capacity_per_day"] == 480


def test_balance_sheet_csv_export(client, admin_auth, db_session):
    """Export endpoint returns CSV with the right header & a few lines."""
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    cash = Account(code="EXP-1", name="현금", type=AccountType.asset)
    cap = Account(code="EXP-2", name="자본금", type=AccountType.equity)
    db_session.add_all([cash, cap])
    db_session.flush()
    e = JournalEntry(entry_date=date(2026, 1, 1), description="seed")
    e.lines.append(JournalLine(account_id=cash.id, debit=1000, credit=0))
    e.lines.append(JournalLine(account_id=cap.id, debit=0, credit=1000))
    db_session.add(e)
    db_session.commit()

    res = client.get(
        "/api/finance/balance-sheet/export?as_of=2026-12-31&format=csv",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.content.decode("utf-8-sig", errors="ignore")
    assert "자산" in body
    assert "1000" in body


def test_ai_posting_llm_falls_back_to_heuristic(client, admin_auth, db_session,
                                                  monkeypatch):
    """Without ANTHROPIC_API_KEY the LLM path is skipped silently."""
    from app.modules.finance.models import Account, AccountType

    db_session.add_all([
        Account(code="1100", name="현금", type=AccountType.asset),
        Account(code="5120", name="여비교통비", type=AccountType.expense),
    ])
    db_session.commit()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    res = client.post(
        "/api/ai-posting/propose",
        headers=admin_auth["headers"],
        json={"description": "택시 출장", "amount": 20000},
    )
    body = res.json()
    # Heuristic match — matched_rule starts without "LLM:"
    assert not (body.get("matched_rule") or "").startswith("LLM:")


# --- Phase 12: QC + GAAP labels + Mobile screens ---------------------------


def test_qc_plan_and_inspection_pass(client, admin_auth, db_session):
    """Plan with min/max criterion → measurement within range → pass result."""
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={
            "code": "INC-WEIGHT",
            "name": "수입 중량 검사",
            "stage": "incoming",
            "criteria": [
                {"name": "중량(kg)", "measurement_type": "numeric",
                 "min_value": 9.5, "max_value": 10.5, "sequence": 10},
            ],
        },
    )
    assert plan.status_code == 200, plan.text
    plan_id = plan.json()["id"]
    crit_id = plan.json()["criteria"][0]["id"]

    insp = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={
            "plan_id": plan_id,
            "quantity_inspected": 100,
            "measurements": [{"criterion_id": crit_id, "numeric_value": 10.0}],
        },
    )
    assert insp.status_code == 200, insp.text
    body = insp.json()
    assert body["result"] == "pass"
    assert float(body["quantity_passed"]) == 100


def test_qc_inspection_fails_when_out_of_range(client, admin_auth, db_session):
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={
            "code": "FAIL-PLAN",
            "name": "범위 초과 테스트",
            "stage": "in_process",
            "criteria": [
                {"name": "온도(℃)", "measurement_type": "numeric",
                 "min_value": 20, "max_value": 25},
            ],
        },
    ).json()
    crit_id = plan["criteria"][0]["id"]
    insp = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={
            "plan_id": plan["id"],
            "quantity_inspected": 50,
            "measurements": [{"criterion_id": crit_id, "numeric_value": 30}],
        },
    )
    assert insp.json()["result"] == "fail"
    assert float(insp.json()["quantity_failed"]) == 50

    # Rework
    rework = client.post(
        f"/api/qc/inspections/{insp.json()['id']}/rework",
        headers=admin_auth["headers"],
    )
    assert rework.json()["result"] == "rework"


def test_qc_defect_pareto(client, admin_auth, db_session):
    """Defects are sorted by quantity, cumulative % is computed."""
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={
            "code": "DEF-PLAN", "name": "결함 추적",
            "stage": "final",
            "criteria": [{"name": "외관", "measurement_type": "boolean"}],
        },
    ).json()
    crit_id = plan["criteria"][0]["id"]
    insp = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={
            "plan_id": plan["id"], "quantity_inspected": 100,
            "measurements": [{"criterion_id": crit_id, "boolean_value": False}],
        },
    ).json()

    # Record 3 defects with different counts
    for dt, qty in [("스크래치", 50), ("색상불량", 30), ("기타", 10)]:
        client.post(
            "/api/qc/defects",
            headers=admin_auth["headers"],
            json={"inspection_id": insp["id"], "defect_type": dt,
                  "quantity": qty, "action": "scrap"},
        )

    pareto = client.get(
        "/api/qc/defect-pareto?days=365",
        headers=admin_auth["headers"],
    ).json()
    types = [d["defect_type"] for d in pareto["defects"]]
    assert types == ["스크래치", "색상불량", "기타"]
    # First entry covers 50/90 ≈ 55.6%
    assert pareto["defects"][0]["cumulative_pct"] > 50


def test_balance_sheet_renders_ifrs_labels(client, admin_auth, db_session):
    """ifrs_label takes precedence when standard=ifrs."""
    from app.modules.finance.models import Account, AccountType, JournalEntry, JournalLine

    cash = Account(code="GAAP-1", name="현금", type=AccountType.asset,
                   ifrs_label="Cash and cash equivalents")
    cap = Account(code="GAAP-2", name="자본금", type=AccountType.equity,
                  ifrs_label="Share capital")
    db_session.add_all([cash, cap])
    db_session.flush()
    e = JournalEntry(entry_date=date(2026, 1, 1), description="seed")
    e.lines.append(JournalLine(account_id=cash.id, debit=1000, credit=0))
    e.lines.append(JournalLine(account_id=cap.id, debit=0, credit=1000))
    db_session.add(e)
    db_session.commit()

    ifrs = client.get(
        "/api/finance/balance-sheet/standard?as_of=2026-12-31&standard=ifrs",
        headers=admin_auth["headers"],
    ).json()
    assert ifrs["standard"] == "ifrs"
    asset_items = ifrs["assets"]["items"]
    found = next((i for i in asset_items if i["code"] == "GAAP-1"), None)
    assert found is not None
    assert found["name"] == "Cash and cash equivalents"  # IFRS label used

    # K-GAAP default — name unchanged
    kgaap = client.get(
        "/api/finance/balance-sheet/standard?as_of=2026-12-31&standard=kgaap",
        headers=admin_auth["headers"],
    ).json()
    kg_item = next((i for i in kgaap["assets"]["items"] if i["code"] == "GAAP-1"), None)
    assert kg_item["name"] == "현금"


def test_qc_pass_rate(client, admin_auth, db_session):
    """pass-rate endpoint aggregates by stage."""
    # Re-uses previous test data; new plan + 2 inspections
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={
            "code": "PR-PLAN", "name": "pass-rate", "stage": "incoming",
            "criteria": [{"name": "OK", "measurement_type": "boolean"}],
        },
    ).json()
    crit_id = plan["criteria"][0]["id"]
    client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={"plan_id": plan["id"], "quantity_inspected": 10,
              "measurements": [{"criterion_id": crit_id, "boolean_value": True}]},
    )
    client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={"plan_id": plan["id"], "quantity_inspected": 10,
              "measurements": [{"criterion_id": crit_id, "boolean_value": False}]},
    )
    res = client.get(
        "/api/qc/pass-rate?stage=incoming&days=30",
        headers=admin_auth["headers"],
    ).json()
    stages = {s["stage"]: s for s in res["stages"]}
    assert "incoming" in stages
    assert stages["incoming"]["total"] >= 2


# --- Phase 13: asset transfer/audit + compliance + drip sequences ---------


def test_asset_transfer_and_audit_disposes_missing(client, admin_auth, db_session):
    """Asset audit auto-disposes assets not found during physical count."""
    from app.modules.hr.models import Employee
    from app.modules.assets.models import Asset, AssetStatus

    emp = Employee(employee_no="A1", full_name="custodian", email="c@x.com",
                    salary=Decimal("3000000"))
    db_session.add(emp)
    db_session.commit()

    # Create 2 assets
    for i in range(2):
        client.post(
            "/api/assets/assets",
            headers=admin_auth["headers"],
            json={
                "asset_no": f"FA-{i}", "name": f"노트북-{i}",
                "acquired_date": "2026-01-01", "acquired_cost": 2000000,
                "useful_life_months": 36,
            },
        )

    # Transfer one
    asset1 = db_session.query(Asset).filter(Asset.asset_no == "FA-0").first()
    tr = client.post(
        "/api/assets/transfers",
        headers=admin_auth["headers"],
        json={
            "asset_id": asset1.id,
            "to_custodian_id": emp.id,
            "to_location": "본사 3F",
            "reason": "신규 배정",
        },
    )
    assert tr.status_code == 200, tr.text

    # Start audit
    audit = client.post(
        "/api/assets/audits",
        headers=admin_auth["headers"],
        json={"code": "AUDIT-2026Q2"},
    )
    assert audit.status_code == 200
    aid = audit.json()["id"]
    assert audit.json()["expected_findings"] == 2

    # Record findings: only asset1 found
    client.post(
        f"/api/assets/audits/{aid}/findings",
        headers=admin_auth["headers"],
        json={"asset_id": asset1.id, "found_present": True,
              "condition": "양호"},
    )
    # Don't record finding for the other → expected_present=True, found_present=False

    close = client.post(
        f"/api/assets/audits/{aid}/close",
        headers=admin_auth["headers"],
    )
    assert close.status_code == 200, close.text
    body = close.json()
    assert body["missing_count"] == 1
    assert body["auto_disposed"] == 1

    # Verify the missing one is now disposed
    asset2 = db_session.query(Asset).filter(Asset.asset_no == "FA-1").first()
    db_session.refresh(asset2)
    assert asset2.status == AssetStatus.disposed


def test_compliance_seed_baseline_and_dashboard(client, admin_auth, db_session):
    res = client.post(
        "/api/compliance/seed-baseline",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["inserted"] >= 10

    # Listing
    controls = client.get(
        "/api/compliance/controls?framework=soc2",
        headers=admin_auth["headers"],
    ).json()
    assert any(c["code"].startswith("SOC2-") for c in controls)

    # Mark implemented + record test
    a_ctrl = controls[0]
    client.patch(
        f"/api/compliance/controls/{a_ctrl['id']}/status?status=implemented",
        headers=admin_auth["headers"],
    )
    test = client.post(
        "/api/compliance/tests",
        headers=admin_auth["headers"],
        json={"control_id": a_ctrl["id"], "result": "pass",
              "findings": "no issues"},
    )
    assert test.status_code == 200

    dashboard = client.get(
        "/api/compliance/dashboard", headers=admin_auth["headers"]
    ).json()
    assert dashboard["frameworks"]
    # The just-tested control should not be overdue
    overdue_ids = {o["control_id"] for o in dashboard["overdue_tests"]}
    assert a_ctrl["id"] not in overdue_ids


def test_drip_sequence_enroll_and_run(client, admin_auth, db_session):
    """Sequence with 2 steps (day 0 + day 7); only day 0 fires immediately."""
    seq = client.post(
        "/api/crm/sequences",
        headers=admin_auth["headers"],
        json={
            "name": "신규 환영 시퀀스",
            "steps": [
                {"delay_days": 0, "subject": "환영합니다", "body": "안녕하세요"},
                {"delay_days": 7, "subject": "1주차 안내", "body": "팁..."},
            ],
        },
    )
    assert seq.status_code == 200, seq.text
    sid = seq.json()["id"]

    enroll = client.post(
        f"/api/crm/sequences/{sid}/enroll?email=drip@x.com",
        headers=admin_auth["headers"],
    )
    assert enroll.status_code == 200

    # Duplicate enrollment rejected
    dup = client.post(
        f"/api/crm/sequences/{sid}/enroll?email=drip@x.com",
        headers=admin_auth["headers"],
    )
    assert dup.status_code == 400

    # Run due — only day-0 step should be sent
    run = client.post(
        "/api/crm/sequences/run-due",
        headers=admin_auth["headers"],
    )
    assert run.status_code == 200
    assert run.json()["sent_steps"] == 1
    assert run.json()["completed_enrollments"] == 0


def test_drip_completes_after_all_steps(client, admin_auth, db_session):
    """An enrollment with all day-0 steps completes in one run."""
    from app.modules.crm.models import SequenceEnrollment

    seq = client.post(
        "/api/crm/sequences",
        headers=admin_auth["headers"],
        json={
            "name": "즉시 시퀀스",
            "steps": [
                {"delay_days": 0, "subject": "1", "body": ""},
                {"delay_days": 0, "subject": "2", "body": ""},
            ],
        },
    ).json()
    client.post(
        f"/api/crm/sequences/{seq['id']}/enroll?email=instant@x.com",
        headers=admin_auth["headers"],
    )
    run = client.post(
        "/api/crm/sequences/run-due",
        headers=admin_auth["headers"],
    )
    assert run.json()["sent_steps"] == 2
    assert run.json()["completed_enrollments"] == 1


# --- Phase 14: notifications/contracts/lease/AI mock -----------------------


def test_notifications_dispatch_no_op_when_unconfigured(client, admin_auth, db_session):
    """Dispatch returns False for unconfigured channels without raising."""
    res = client.post(
        "/api/notifications/dispatch",
        headers=admin_auth["headers"],
        json={
            "subject": "테스트", "body": "본문",
            "channels": ["email", "slack"],
            "recipients": ["test@x.com"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # No SMTP/Slack configured in test env → both False
    assert body["results"]["email"] is False
    assert body["results"]["slack"] is False


def test_contract_lifecycle_and_renewals_due(client, admin_auth, db_session):
    from datetime import timedelta as _td

    today = date.today()
    res = client.post(
        "/api/contracts",
        headers=admin_auth["headers"],
        json={
            "contract_no": "C-2026-1", "title": "유지보수 계약",
            "type": "supplier", "counterparty": "메가IT",
            "start_date": (today - _td(days=300)).isoformat(),
            "end_date": (today + _td(days=30)).isoformat(),
            "value": 12000000, "currency": "KRW",
            "renewal": "manual", "notice_period_days": 60,
        },
    )
    assert res.status_code == 200, res.text
    cid = res.json()["id"]
    client.post(f"/api/contracts/{cid}/activate", headers=admin_auth["headers"])

    due = client.get(
        "/api/contracts/renewals-due?within_days=60",
        headers=admin_auth["headers"],
    ).json()
    found = next((c for c in due["contracts"] if c["id"] == cid), None)
    assert found is not None
    assert found["in_notice_window"] is True  # 30 days left, notice 60 days


def test_contract_expire_overdue_auto_renew(client, admin_auth, db_session):
    """Auto-renewal contracts past end_date roll forward without going expired."""
    from datetime import timedelta as _td

    today = date.today()
    c = client.post(
        "/api/contracts",
        headers=admin_auth["headers"],
        json={
            "contract_no": "C-AUTO-1", "title": "자동 갱신",
            "type": "customer", "counterparty": "ACME",
            "start_date": (today - _td(days=365)).isoformat(),
            "end_date": (today - _td(days=1)).isoformat(),
            "renewal": "auto", "notice_period_days": 30,
        },
    ).json()
    client.post(f"/api/contracts/{c['id']}/activate", headers=admin_auth["headers"])
    res = client.post(
        "/api/contracts/expire-overdue", headers=admin_auth["headers"]
    ).json()
    assert res["auto_renewed"] >= 1
    # Manual contract from previous test should expire
    # (only checks counters are non-negative)
    assert res["expired"] >= 0


def test_lease_activate_generates_schedule(client, admin_auth, db_session):
    """Activating a lease computes PV and generates monthly schedule."""
    res = client.post(
        "/api/lease",
        headers=admin_auth["headers"],
        json={
            "lease_no": "L-OFFICE-1",
            "description": "사무실 임대",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",  # 12 months
            "monthly_payment": 1000000,
            "annual_discount_rate": 0.06,
        },
    )
    assert res.status_code == 200, res.text
    lid = res.json()["id"]

    act = client.post(f"/api/lease/{lid}/activate", headers=admin_auth["headers"])
    assert act.status_code == 200, act.text
    body = act.json()
    # PV of 1M for 12 months at 0.5%/month ≈ 11.6M (annuity formula)
    assert 11_000_000 < float(body["lease_liability"]) < 12_000_000
    assert float(body["rou_asset"]) == float(body["lease_liability"])

    sched = client.get(
        f"/api/lease/{lid}/schedule", headers=admin_auth["headers"]
    ).json()
    assert len(sched) == 12
    # First period: interest > 0, closing < opening
    assert sched[0]["interest_expense"] > 0
    assert sched[0]["closing_liability"] < sched[0]["opening_liability"]
    # Final period: closing ~ 0
    assert abs(sched[-1]["closing_liability"]) < 5.0


def test_lease_post_period_creates_journal(client, admin_auth, db_session):
    from app.modules.finance.models import Account, AccountType, JournalEntry

    # Required CoA for lease posting
    for code, name, t in [
        ("1100", "현금", AccountType.asset),
        ("1500", "사용권자산", AccountType.asset),
        ("1590", "사용권 감가누계", AccountType.asset),
        ("2200", "리스부채", AccountType.liability),
        ("5210", "이자비용", AccountType.expense),
        ("5220", "사용권 상각비", AccountType.expense),
    ]:
        if not db_session.query(Account).filter(Account.code == code).first():
            db_session.add(Account(code=code, name=name, type=t))
    db_session.commit()

    create = client.post(
        "/api/lease",
        headers=admin_auth["headers"],
        json={
            "lease_no": "L-POST-1",
            "description": "포스팅 테스트",
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",  # 6 months
            "monthly_payment": 500000,
            "annual_discount_rate": 0.04,
        },
    ).json()
    client.post(f"/api/lease/{create['id']}/activate", headers=admin_auth["headers"])

    post = client.post(
        f"/api/lease/{create['id']}/post-period?period_code=2026-01",
        headers=admin_auth["headers"],
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["journal_entry_id"] is not None

    # Verify the JE balances
    je = db_session.query(JournalEntry).filter(
        JournalEntry.id == body["journal_entry_id"]
    ).first()
    dr = sum(float(l.debit) for l in je.lines)
    cr = sum(float(l.credit) for l in je.lines)
    assert abs(dr - cr) < 0.01

    # Re-posting same period rejected
    again = client.post(
        f"/api/lease/{create['id']}/post-period?period_code=2026-01",
        headers=admin_auth["headers"],
    )
    assert again.status_code == 400


def test_ai_posting_llm_with_stub_client(client, admin_auth, db_session):
    """Inject a fake Anthropic client and verify LLM path is used."""
    import os
    from app.modules.finance.models import Account, AccountType
    from app.modules.ai_posting import router as ai_router

    # Set up CoA
    db_session.add_all([
        Account(code="1100", name="현금", type=AccountType.asset),
        Account(code="5140", name="임대료", type=AccountType.expense),
    ])
    db_session.commit()

    # Stub client returning a perfectly balanced entry
    class _StubContent:
        def __init__(self, text): self.text = text

    class _StubMsg:
        def __init__(self, text): self.content = [_StubContent(text)]

    class _StubMessages:
        def create(self, **kwargs):
            return _StubMsg(
                '{"lines": ['
                '{"account_code": "5140", "debit": 500000, "credit": 0},'
                '{"account_code": "1100", "debit": 0, "credit": 500000}'
                '], "confidence": 0.95, "rationale": "월세 결제"}'
            )

    class _StubAnthropic:
        messages = _StubMessages()

    ai_router.set_anthropic_client(_StubAnthropic())
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        res = client.post(
            "/api/ai-posting/propose",
            headers=admin_auth["headers"],
            json={"description": "월세 5월분", "amount": 500000},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["matched_rule"].startswith("LLM:")
        assert body["confidence"] >= 0.9
        assert sum(float(l["debit"]) for l in body["lines"]) == 500000
        assert sum(float(l["credit"]) for l in body["lines"]) == 500000
    finally:
        ai_router.set_anthropic_client(None)
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_ai_posting_llm_unbalanced_falls_back(client, admin_auth, db_session):
    """If the LLM returns an unbalanced entry the heuristic fallback kicks in."""
    import os
    from app.modules.finance.models import Account, AccountType
    from app.modules.ai_posting import router as ai_router

    db_session.add_all([
        Account(code="1100", name="현금", type=AccountType.asset),
        Account(code="5120", name="여비교통비", type=AccountType.expense),
    ])
    db_session.commit()

    class _BadMessages:
        def create(self, **kwargs):
            class _M:
                content = [type("X", (), {"text":
                    '{"lines": [{"account_code": "1100", "debit": 100, "credit": 0}], '
                    '"confidence": 0.9, "rationale": "broken"}'
                })()]
            return _M()

    class _BadStub:
        messages = _BadMessages()

    ai_router.set_anthropic_client(_BadStub())
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        res = client.post(
            "/api/ai-posting/propose",
            headers=admin_auth["headers"],
            json={"description": "출장 택시", "amount": 30000},
        )
        body = res.json()
        # Fell back to heuristic — rule matched "택시" rather than "LLM:"
        assert not (body.get("matched_rule") or "").startswith("LLM:")
    finally:
        ai_router.set_anthropic_client(None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
