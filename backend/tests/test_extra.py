"""Coverage for the previously-untested modules."""
from decimal import Decimal


# --- Backup masking ---------------------------------------------------------


def test_backup_redacts_secrets_by_default(client, admin_auth):
    res = client.get("/api/admin/backup", headers=admin_auth["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["redacted"] is True
    users = body["tables"].get("users", [])
    assert users, "expected at least one user in the backup"
    assert all(u["hashed_password"] == "***REDACTED***" for u in users)


def test_backup_with_secrets_optin(client, admin_auth):
    res = client.get(
        "/api/admin/backup?include_secrets=true", headers=admin_auth["headers"]
    )
    assert res.status_code == 200
    body = res.json()
    assert body["redacted"] is False
    assert body["tables"]["users"][0]["hashed_password"].startswith("$2")


# --- Tenant scoping ---------------------------------------------------------


def test_tenant_header_scopes_customers(client, admin_auth, db_session):
    from app.modules.sales.models import Customer
    from app.modules.tenants.models import Tenant

    t1 = Tenant(code="T1", name="T1")
    t2 = Tenant(code="T2", name="T2")
    db_session.add_all([t1, t2])
    db_session.commit()
    db_session.refresh(t1)
    db_session.refresh(t2)
    db_session.add(Customer(name="C1", tenant_id=t1.id))
    db_session.add(Customer(name="C2", tenant_id=t2.id))
    db_session.commit()

    h1 = {**admin_auth["headers"], "X-Tenant-ID": str(t1.id)}
    res1 = client.get("/api/sales/customers", headers=h1)
    assert res1.status_code == 200
    names1 = [c["name"] for c in res1.json()["items"]]
    assert "C1" in names1 and "C2" not in names1


# --- RLS owner filter -------------------------------------------------------


def test_rls_staff_sees_only_own_customers(client, admin_auth, db_session):
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    staff = User(
        email="rls@test.com",
        full_name="R",
        hashed_password=hash_password("test1234"),
        role=Role.staff,
    )
    db_session.add(staff)
    db_session.commit()

    # admin creates one customer
    client.post(
        "/api/sales/customers",
        headers=admin_auth["headers"],
        json={"name": "AdminCustomer"},
    )

    # staff logs in and creates one
    staff_h = {
        "Authorization": "Bearer "
        + client.post(
            "/api/auth/login",
            data={"username": "rls@test.com", "password": "test1234"},
        ).json()["access_token"]
    }
    client.post(
        "/api/sales/customers",
        headers=staff_h,
        json={"name": "StaffCustomer"},
    )

    own = client.get("/api/sales/customers", headers=staff_h).json()["items"]
    assert {c["name"] for c in own} == {"StaffCustomer"}


# --- Currency conversion ----------------------------------------------------


def test_currency_convert(client, admin_auth, db_session):
    from app.modules.currencies.models import Currency, ExchangeRate

    krw = Currency(code="KRW", name="Won", symbol="₩", is_base=True)
    usd = Currency(code="USD", name="Dollar", symbol="$")
    db_session.add_all([krw, usd])
    db_session.commit()
    db_session.refresh(usd)
    db_session.add(ExchangeRate(currency_id=usd.id, rate_to_base=Decimal("1300")))
    db_session.commit()

    res = client.get(
        "/api/currencies/convert?amount=100&from=USD&to=KRW",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    assert Decimal(res.json()["converted"]) == Decimal("130000")


# --- Sales order confirm pre-flight ----------------------------------------


def test_confirm_order_atomicity(client, admin_auth, db_session):
    """If line N has insufficient stock, lines 1..N-1 must NOT be decremented."""
    from app.modules.inventory.models import Item

    a = Item(sku="A1", name="A", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("100"))
    b = Item(sku="B1", name="B", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("5"))
    db_session.add_all([a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)

    cust = client.post(
        "/api/sales/customers",
        headers=admin_auth["headers"],
        json={"name": "CustAtomic"},
    ).json()

    so = client.post(
        "/api/sales/orders",
        headers=admin_auth["headers"],
        json={
            "order_no": "SO-ATOMIC-1",
            "customer_id": cust["id"],
            "items": [
                {"item_id": a.id, "quantity": 10, "unit_price": 1},
                {"item_id": b.id, "quantity": 50, "unit_price": 1},
            ],
        },
    ).json()

    res = client.post(
        f"/api/sales/orders/{so['id']}/confirm", headers=admin_auth["headers"]
    )
    assert res.status_code == 400
    assert "Insufficient" in res.json()["error"]["message"]

    # CRITICAL: item A must NOT have been decremented.
    db_session.refresh(a)
    db_session.refresh(b)
    assert Decimal(a.stock_qty) == Decimal("100")
    assert Decimal(b.stock_qty) == Decimal("5")


# --- Ledger verify ---------------------------------------------------------


def test_ledger_verify_detects_tampering(client, admin_auth, db_session):
    from app.modules.inventory.models import Item
    from app.modules.ledger.models import LedgerEntry

    a = Item(sku="LDG", name="L", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("100"))
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={"item_id": a.id, "type": "outbound", "quantity": 5},
    )
    res = client.get("/api/ledger/verify", headers=admin_auth["headers"])
    assert res.status_code == 200
    assert res.json()["valid"] is True

    # Tamper with the latest entry's payload, recheck
    entry = db_session.query(LedgerEntry).order_by(LedgerEntry.seq.desc()).first()
    entry.payload = '{"tampered": true}'
    db_session.commit()
    res = client.get("/api/ledger/verify", headers=admin_auth["headers"])
    assert res.json()["valid"] is False


# --- Security headers + error envelope -------------------------------------


def test_security_headers_set(client):
    res = client.get("/api/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"


def test_error_envelope_shape(client, admin_auth):
    res = client.get(
        "/api/inventory/items/999999/lots", headers=admin_auth["headers"]
    )
    # 404 from a missing item — but `list_lots` returns []. Use a clearer trigger:
    res = client.delete("/api/auth/users/999999", headers=admin_auth["headers"])
    assert res.status_code == 404
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]
