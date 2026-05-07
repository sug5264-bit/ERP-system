from decimal import Decimal


def _create_supplier(client, headers):
    res = client.post(
        "/api/suppliers",
        headers=headers,
        json={"code": "SUP-T1", "name": "Test Supplier"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _create_item(db_session, sku="WG-S-001"):
    from app.modules.inventory.models import Item

    item = Item(sku=sku, name="Item", unit="EA", unit_price=Decimal("100"), stock_qty=Decimal("0"))
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_supplier_listing_blocked_for_supplier_role(client, db_session, admin_auth):
    """Supplier-portal users cannot list other suppliers."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    sup_user = User(
        email="sup@test.com",
        full_name="Sup",
        hashed_password=hash_password("test1234"),
        role=Role.supplier,
    )
    db_session.add(sup_user)
    db_session.commit()

    sup_login = client.post(
        "/api/auth/login",
        data={"username": "sup@test.com", "password": "test1234"},
    ).json()
    sup_h = {"Authorization": f"Bearer {sup_login['access_token']}"}

    res = client.get("/api/suppliers", headers=sup_h)
    assert res.status_code == 403


def test_supplier_blocked_from_internal_modules(client, db_session):
    """Supplier user cannot hit /api/sales, /api/inventory, etc."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    sup_user = User(
        email="sup2@test.com",
        full_name="S",
        hashed_password=hash_password("test1234"),
        role=Role.supplier,
    )
    db_session.add(sup_user)
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        data={"username": "sup2@test.com", "password": "test1234"},
    ).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}

    for path in ["/api/sales/orders", "/api/inventory/items", "/api/finance/accounts"]:
        res = client.get(path, headers=h)
        assert res.status_code == 403, f"{path} should be 403, got {res.status_code}"


def test_po_state_machine_and_inbound_movement(client, admin_auth, db_session):
    item = _create_item(db_session, sku="WG-S-PO-1")
    sup = _create_supplier(client, admin_auth["headers"])

    res = client.post(
        "/api/suppliers/orders",
        headers=admin_auth["headers"],
        json={
            "po_no": "PO-T-001",
            "supplier_id": sup["id"],
            "items": [{"item_id": item.id, "quantity": 100, "unit_price": 50}],
        },
    )
    assert res.status_code == 200
    po_id = res.json()["id"]

    for action in ("send", "acknowledge", "ship"):
        r = client.post(
            f"/api/suppliers/orders/{po_id}/{action}", headers=admin_auth["headers"]
        )
        assert r.status_code == 200, f"{action}: {r.text}"

    # Receive: stock should jump from 0 to 100
    r = client.post(
        f"/api/suppliers/orders/{po_id}/receive",
        headers=admin_auth["headers"],
        json={"lines": [{"item_id": item.id, "quantity": 100}]},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "received"

    db_session.refresh(item)
    assert Decimal(item.stock_qty) == Decimal("100")


def test_invalid_state_transition_rejected(client, admin_auth, db_session):
    item = _create_item(db_session, sku="WG-S-PO-2")
    sup = _create_supplier(client, admin_auth["headers"])
    res = client.post(
        "/api/suppliers/orders",
        headers=admin_auth["headers"],
        json={
            "po_no": "PO-T-002",
            "supplier_id": sup["id"],
            "items": [{"item_id": item.id, "quantity": 5, "unit_price": 1}],
        },
    )
    po_id = res.json()["id"]

    # Cannot acknowledge a draft (must send first)
    r = client.post(
        f"/api/suppliers/orders/{po_id}/acknowledge", headers=admin_auth["headers"]
    )
    assert r.status_code == 400
