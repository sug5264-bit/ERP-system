"""Verify admin-only PATCH/DELETE on core business modules.

Each test confirms:
  1. admin can edit / delete and the change reaches the DB
  2. non-admin (manager/staff) gets 403 on the same call
  3. cascade-protection rules (non-zero stock, existing orders, etc.) hold
"""
from decimal import Decimal


def _login(client, email, pw="test1234"):
    res = client.post("/api/auth/login", data={"username": email, "password": pw})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _make_user(db_session, email, role):
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    u = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=hash_password("test1234"),
        role=getattr(Role, role),
    )
    db_session.add(u)
    db_session.commit()
    return u


# ---- inventory items -------------------------------------------------------


def test_admin_can_edit_item(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    item = Item(sku="EDIT-1", name="원래 이름", unit="EA", unit_price=Decimal("100"), stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    res = client.patch(
        f"/api/inventory/items/{item.id}",
        headers=admin_auth["headers"],
        json={"name": "변경된 이름", "unit_price": 250},
    )
    assert res.status_code == 200
    db_session.refresh(item)
    assert item.name == "변경된 이름"
    assert Decimal(item.unit_price) == Decimal("250")


def test_non_admin_cannot_edit_item(client, db_session):
    from app.modules.inventory.models import Item

    _make_user(db_session, "mgr@test.com", "manager")
    item = Item(sku="EDIT-2", name="x", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()

    res = client.patch(
        f"/api/inventory/items/{item.id}",
        headers=_login(client, "mgr@test.com"),
        json={"name": "y"},
    )
    assert res.status_code == 403


def test_delete_item_blocked_when_has_stock(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    item = Item(sku="DEL-1", name="x", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("5"))
    db_session.add(item)
    db_session.commit()

    res = client.delete(f"/api/inventory/items/{item.id}", headers=admin_auth["headers"])
    assert res.status_code == 409
    assert "non-zero stock" in res.json()["error"]["message"]


def test_delete_item_when_clean(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    item = Item(sku="DEL-2", name="x", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()

    res = client.delete(f"/api/inventory/items/{item.id}", headers=admin_auth["headers"])
    assert res.status_code == 200
    assert db_session.query(Item).filter(Item.sku == "DEL-2").first() is None


# ---- sales customers + orders ---------------------------------------------


def test_admin_edits_customer(client, admin_auth, db_session):
    from app.modules.sales.models import Customer

    c = Customer(name="원래", email="old@test.com")
    db_session.add(c)
    db_session.commit()

    res = client.patch(
        f"/api/sales/customers/{c.id}",
        headers=admin_auth["headers"],
        json={"name": "변경", "company": "WG Corp"},
    )
    assert res.status_code == 200
    db_session.refresh(c)
    assert c.name == "변경"
    assert c.company == "WG Corp"


def test_delete_customer_blocked_when_has_orders(client, admin_auth, db_session):
    from datetime import date
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder

    c = Customer(name="orderful")
    db_session.add(c)
    db_session.flush()
    db_session.add(
        SalesOrder(
            order_no="SO-DEL-1",
            customer_id=c.id,
            order_date=date.today(),
            status=OrderStatus.draft,
            total=0,
        )
    )
    db_session.commit()

    res = client.delete(f"/api/sales/customers/{c.id}", headers=admin_auth["headers"])
    assert res.status_code == 409


def test_delete_order_only_when_draft(client, admin_auth, db_session):
    from datetime import date
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder

    c = Customer(name="x")
    db_session.add(c)
    db_session.flush()
    confirmed = SalesOrder(
        order_no="SO-CONF",
        customer_id=c.id,
        order_date=date.today(),
        status=OrderStatus.confirmed,
        total=0,
    )
    draft = SalesOrder(
        order_no="SO-DR",
        customer_id=c.id,
        order_date=date.today(),
        status=OrderStatus.draft,
        total=0,
    )
    db_session.add_all([confirmed, draft])
    db_session.commit()

    r1 = client.delete(f"/api/sales/orders/{confirmed.id}", headers=admin_auth["headers"])
    assert r1.status_code == 409

    r2 = client.delete(f"/api/sales/orders/{draft.id}", headers=admin_auth["headers"])
    assert r2.status_code == 200


# ---- finance: account delete + journal void --------------------------------


def test_finance_journal_void_creates_reversing_entry(client, admin_auth, db_session):
    from datetime import date
    from app.modules.finance.models import (
        Account,
        AccountType,
        JournalEntry,
        JournalLine,
    )

    cash = Account(code="C", name="cash", type=AccountType.asset)
    rev = Account(code="R", name="rev", type=AccountType.revenue)
    db_session.add_all([cash, rev])
    db_session.flush()
    je = JournalEntry(entry_date=date.today(), description="sale", reference="x")
    je.lines.append(JournalLine(account_id=cash.id, debit=100, credit=0))
    je.lines.append(JournalLine(account_id=rev.id, debit=0, credit=100))
    db_session.add(je)
    db_session.commit()

    res = client.post(
        f"/api/finance/journal-entries/{je.id}/void",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reference"] == f"VOID-{je.id}"
    # Reversed dr/cr
    by_acc = {l["account_id"]: l for l in body["lines"]}
    assert Decimal(by_acc[cash.id]["credit"]) == Decimal("100")
    assert Decimal(by_acc[rev.id]["debit"]) == Decimal("100")


def test_delete_account_blocked_when_has_lines(client, admin_auth, db_session):
    from datetime import date
    from app.modules.finance.models import (
        Account,
        AccountType,
        JournalEntry,
        JournalLine,
    )

    a = Account(code="ZZ", name="z", type=AccountType.asset)
    db_session.add(a)
    db_session.flush()
    je = JournalEntry(entry_date=date.today(), description="x")
    je.lines.append(JournalLine(account_id=a.id, debit=1, credit=0))
    db_session.add(je)
    db_session.commit()

    res = client.delete(
        f"/api/finance/accounts/{a.id}", headers=admin_auth["headers"]
    )
    assert res.status_code == 409


# ---- suppliers + HR departments -------------------------------------------


def test_admin_edits_supplier(client, admin_auth, db_session):
    from app.modules.suppliers.models import Supplier

    s = Supplier(code="SUP-E", name="원래", contact_email="old@vendor.com")
    db_session.add(s)
    db_session.commit()

    res = client.patch(
        f"/api/suppliers/{s.id}",
        headers=admin_auth["headers"],
        json={"name": "변경된", "is_active": False},
    )
    assert res.status_code == 200
    db_session.refresh(s)
    assert s.name == "변경된"
    assert s.is_active is False


def test_delete_department_blocked_with_employees(client, admin_auth, db_session):
    from datetime import date
    from app.modules.hr.models import Department, Employee

    d = Department(name="ENG")
    db_session.add(d)
    db_session.flush()
    db_session.add(
        Employee(
            employee_no="E-1",
            full_name="X",
            email="x@test.com",
            hire_date=date.today(),
            salary=0,
            department_id=d.id,
        )
    )
    db_session.commit()

    res = client.delete(f"/api/hr/departments/{d.id}", headers=admin_auth["headers"])
    assert res.status_code == 409
