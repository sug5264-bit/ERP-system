"""Deep verification of audit's 'false positive' claims.

Each test in this file directly reproduces an audit-reported scenario to
either confirm the false-positive verdict or expose a real bug.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest


# ---- #1 AI accept_proposal partial-commit claim --------------------------


def test_ai_accept_unknown_account_no_partial_commit(
    client, admin_auth, db_session
):
    """Agent #4: claimed mid-loop exception leaves partial JE in DB.

    Reality check: if line 2's account is unknown → 400 raised → DB should
    have NO JournalEntry rows created.
    """
    from app.modules.finance.models import Account, AccountType, JournalEntry

    db_session.add_all([
        Account(code="1100", name="현금", type=AccountType.asset),
        # Note: "9999" deliberately NOT created
    ])
    db_session.commit()
    before = db_session.query(JournalEntry).filter(
        JournalEntry.reference == "AI-PROP"
    ).count()

    proposal = {
        "description": "test",
        "confidence": 0.9,  # force flag not needed
        "matched_rule": "manual",
        "lines": [
            {"account_code": "1100", "debit": "1000", "credit": "0"},
            {"account_code": "9999", "debit": "0", "credit": "1000"},  # bad
        ],
    }
    res = client.post(
        "/api/ai-posting/accept?description=test",
        headers=admin_auth["headers"],
        json=proposal,
    )
    assert res.status_code == 400
    after = db_session.query(JournalEntry).filter(
        JournalEntry.reference == "AI-PROP"
    ).count()
    # No partial commit — same count
    assert after == before, "Partial commit detected — REAL BUG"


# ---- #2 synchronize_session=False on lease re-activate -------------------


def test_lease_reactivate_replaces_schedule_cleanly(client, admin_auth, db_session):
    """Agent #2 claimed re-activation creates duplicate schedule rows.

    Reality check: activate an already-active lease should be rejected
    (precondition: status == draft). Only fresh activation creates schedule.
    """
    res = client.post(
        "/api/lease",
        headers=admin_auth["headers"],
        json={
            "lease_no": "L-VERIFY-2", "description": "verify",
            "start_date": "2026-01-01", "end_date": "2026-06-30",
            "monthly_payment": 1000, "annual_discount_rate": 0.05,
        },
    )
    lid = res.json()["id"]
    a1 = client.post(f"/api/lease/{lid}/activate", headers=admin_auth["headers"])
    assert a1.status_code == 200
    sched_count = len(client.get(
        f"/api/lease/{lid}/schedule", headers=admin_auth["headers"]
    ).json())

    # Try re-activating an already-active lease → rejected
    a2 = client.post(f"/api/lease/{lid}/activate", headers=admin_auth["headers"])
    assert a2.status_code == 400, "Re-activation should be blocked"
    # Schedule unchanged
    new_count = len(client.get(
        f"/api/lease/{lid}/schedule", headers=admin_auth["headers"]
    ).json())
    assert new_count == sched_count


# ---- #3 Lease post-period race --------------------------------------------


def test_lease_post_period_idempotent(client, admin_auth, db_session):
    """Agent #10 claimed race; check that double-post is blocked."""
    from app.modules.finance.models import Account, AccountType

    for code, name, t in [
        ("1100", "현금", AccountType.asset),
        ("1590", "감가누계", AccountType.asset),
        ("2200", "리스부채", AccountType.liability),
        ("5210", "이자비용", AccountType.expense),
        ("5220", "상각비", AccountType.expense),
    ]:
        if not db_session.query(Account).filter(Account.code == code).first():
            db_session.add(Account(code=code, name=name, type=t))
    db_session.commit()

    create = client.post(
        "/api/lease",
        headers=admin_auth["headers"],
        json={
            "lease_no": "L-RACE-1", "description": "race",
            "start_date": "2026-01-01", "end_date": "2026-03-31",
            "monthly_payment": 1000, "annual_discount_rate": 0.05,
        },
    ).json()
    client.post(f"/api/lease/{create['id']}/activate", headers=admin_auth["headers"])

    # Post the same period twice in quick succession (single-thread but tests
    # the `posted` flag idempotency that real with_for_update relies on).
    r1 = client.post(
        f"/api/lease/{create['id']}/post-period?period_code=2026-01",
        headers=admin_auth["headers"],
    )
    r2 = client.post(
        f"/api/lease/{create['id']}/post-period?period_code=2026-01",
        headers=admin_auth["headers"],
    )
    assert r1.status_code == 200
    assert r2.status_code == 400, "Second post must be rejected"


@pytest.mark.skip(
    reason="Test fixture shares db_session across threads which is "
           "thread-unsafe (SQLAlchemy session). In production each request "
           "gets its own session, so this test can't reliably reproduce the "
           "real concurrency behavior. Idempotency is covered by the "
           "synchronous test above; true thread-safety in production relies "
           "on with_for_update + per-request sessions."
)
def test_lease_post_period_concurrent_threads():
    pass


# ---- #4 Recipe IDOR — verify no current path -------------------------------


def test_recipe_no_update_or_delete_endpoint_exists():
    """Agent #5 worried about future IDOR. Verify endpoints don't exist."""
    from app.modules.fnb import router

    paths = [
        (route.path, route.methods) for route in router.router.routes
    ]
    update_or_delete = [
        p for p, m in paths
        if "/recipes" in p and m & {"PATCH", "PUT", "DELETE"}
    ]
    assert update_or_delete == [], (
        f"Found update/delete recipe endpoints {update_or_delete} — "
        "IDOR concern becomes real"
    )


# ---- #5 QC mixed-result — Pydantic enforcement ----------------------------


def test_qc_inspection_empty_measurements_rejected(client, admin_auth, db_session):
    """Pydantic min_length=1 should reject empty measurements list."""
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={
            "code": "VER-Q1", "name": "verify",
            "stage": "incoming",
            "criteria": [{"name": "ok", "measurement_type": "boolean"}],
        },
    ).json()
    res = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={"plan_id": plan["id"], "quantity_inspected": 100,
              "measurements": []},
    )
    # Pydantic returns 422 for validation errors
    assert res.status_code == 422


def test_qc_quantity_invariant(client, admin_auth, db_session):
    """quantity_passed + quantity_failed == quantity_inspected (current code path)."""
    plan = client.post(
        "/api/qc/plans",
        headers=admin_auth["headers"],
        json={"code": "VER-Q2", "name": "verify",
              "stage": "incoming",
              "criteria": [{"name": "x", "measurement_type": "boolean"}]},
    ).json()
    # Pass case
    p = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={"plan_id": plan["id"], "quantity_inspected": 50,
              "measurements": [{"criterion_id": plan["criteria"][0]["id"],
                                "boolean_value": True}]},
    ).json()
    assert Decimal(p["quantity_passed"]) + Decimal(p["quantity_failed"]) == Decimal("50")
    # Fail case
    f = client.post(
        "/api/qc/inspections",
        headers=admin_auth["headers"],
        json={"plan_id": plan["id"], "quantity_inspected": 30,
              "measurements": [{"criterion_id": plan["criteria"][0]["id"],
                                "boolean_value": False}]},
    ).json()
    assert Decimal(f["quantity_passed"]) + Decimal(f["quantity_failed"]) == Decimal("30")


# ---- #6 Depreciation partial commit ---------------------------------------


def test_depreciation_run_atomic_on_failure(client, admin_auth, db_session, monkeypatch):
    """Inject a failure mid-loop and verify no partial state."""
    from app.modules.finance.models import Account, AccountType
    from app.modules.assets import router as assets_router
    from app.modules.assets.models import Asset, DepreciationEntry

    # Seed accounts so dep would normally proceed
    db_session.add_all([
        Account(code="5200", name="감가상각비", type=AccountType.expense),
        Account(code="1390", name="감가누계", type=AccountType.asset),
    ])
    db_session.commit()

    # Create 3 assets
    for i in range(3):
        client.post(
            "/api/assets/assets",
            headers=admin_auth["headers"],
            json={
                "asset_no": f"DA-{i}", "name": f"a{i}",
                "acquired_date": "2026-01-01", "acquired_cost": 1200,
                "useful_life_months": 12,
            },
        )

    # Patch _monthly_amount to raise on the 2nd asset
    original = assets_router._monthly_amount
    call_count = {"n": 0}

    def failing(asset):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("injected failure")
        return original(asset)

    monkeypatch.setattr(assets_router, "_monthly_amount", failing)

    # TestClient propagates RuntimeError as Python exception (not 500). Catch it.
    with pytest.raises(RuntimeError, match="injected failure"):
        client.post(
            "/api/assets/depreciation/run?period_code=2026-05",
            headers=admin_auth["headers"],
        )

    # In production each request has its own Session that close()s on exception
    # (auto-rollback). The test fixture shares db_session with the endpoint, so
    # explicitly rollback to simulate that behavior before checking DB state.
    db_session.rollback()

    # All-or-nothing: NO depreciation entries should exist for any asset
    entries = db_session.query(DepreciationEntry).filter(
        DepreciationEntry.period_code == "2026-05"
    ).count()
    assert entries == 0, (
        f"Partial commit detected: {entries} entries exist after failure"
    )
    # Asset accumulated_depreciation also untouched
    for a in db_session.query(Asset).filter(Asset.asset_no.like("DA-%")).all():
        assert Decimal(a.accumulated_depreciation) == 0, (
            f"Asset {a.asset_no} partially updated: {a.accumulated_depreciation}"
        )


# ---- #7 Concurrency: PO + GR same time ------------------------------------


def test_pick_list_creation_idempotent(client, admin_auth, db_session):
    """Sequential duplicate generation: pick_no uniqueness prevents duplicates."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem

    item = Item(sku="CON-ITEM", name="con", stock_qty=Decimal("100"))
    cust = Customer(name="CON")
    db_session.add_all([item, cust])
    db_session.flush()
    so = SalesOrder(order_no="SO-CON-1", customer_id=cust.id,
                     status=OrderStatus.confirmed, total=Decimal("0"))
    so.items.append(SalesOrderItem(item_id=item.id, quantity=Decimal("5"),
                                     unit_price=Decimal("10")))
    db_session.add(so)
    db_session.commit()

    r1 = client.post(
        f"/api/wms/pick-lists/from-order/{so.id}",
        headers=admin_auth["headers"],
    )
    r2 = client.post(
        f"/api/wms/pick-lists/from-order/{so.id}",
        headers=admin_auth["headers"],
    )
    r3 = client.post(
        f"/api/wms/pick-lists/from-order/{so.id}",
        headers=admin_auth["headers"],
    )
    assert r1.status_code == 200
    assert r2.status_code == 400
    assert r3.status_code == 400


# ---- #8 Overpayment concurrent — Quote→Pay race ----------------------------


def test_sequential_overpayment_rejected(client, admin_auth, db_session):
    """Sequential pay 600 + pay 600 on a 1000 invoice — second is overpay."""
    from app.modules.finance.models import Account, AccountType
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer

    for code, name, t in [
        ("1100", "현금", AccountType.asset),
        ("1200", "AR", AccountType.asset),
        ("2150", "VAT", AccountType.liability),
        ("4100", "매출", AccountType.revenue),
    ]:
        if not db_session.query(Account).filter(Account.code == code).first():
            db_session.add(Account(code=code, name=name, type=t))
    item = Item(sku="OP-1", name="op", stock_qty=Decimal("100"),
                unit_price=Decimal("100"))
    cust = Customer(name="OP cust")
    db_session.add_all([item, cust])
    db_session.commit()

    inv = client.post(
        "/api/billing/invoices",
        headers=admin_auth["headers"],
        json={
            "invoice_no": "INV-OP-1", "customer_id": cust.id,
            "items": [{"description": "x", "item_id": item.id,
                       "quantity": 10, "unit_price": 100}],
            "tax_rate": 0,
        },
    ).json()
    client.post(f"/api/billing/invoices/{inv['id']}/issue",
                 headers=admin_auth["headers"])

    p1 = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 600},
    )
    p2 = client.post(
        "/api/billing/payments",
        headers=admin_auth["headers"],
        json={"invoice_id": inv["id"], "amount": 600},
    )
    assert p1.status_code == 200
    assert p2.status_code == 400  # overpay: 600 + 600 = 1200 > 1000
