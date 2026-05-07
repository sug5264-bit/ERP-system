from decimal import Decimal


def _create_item(db_session, **kw):
    from app.modules.inventory.models import Item

    defaults = dict(
        sku="WG-TEST-001",
        name="Test Item",
        unit="EA",
        unit_price=Decimal("1000"),
        stock_qty=Decimal("100"),
    )
    defaults.update(kw)
    item = Item(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_inbound_increases_stock(client, admin_auth, db_session):
    item = _create_item(db_session)
    res = client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={"item_id": item.id, "type": "inbound", "quantity": 50},
    )
    assert res.status_code == 200
    db_session.refresh(item)
    assert Decimal(item.stock_qty) == Decimal("150")


def test_outbound_decreases_stock(client, admin_auth, db_session):
    item = _create_item(db_session)
    res = client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={"item_id": item.id, "type": "outbound", "quantity": 30},
    )
    assert res.status_code == 200
    db_session.refresh(item)
    assert Decimal(item.stock_qty) == Decimal("70")


def test_outbound_blocks_negative_stock(client, admin_auth, db_session):
    item = _create_item(db_session, stock_qty=Decimal("10"))
    res = client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={"item_id": item.id, "type": "outbound", "quantity": 50},
    )
    assert res.status_code == 400
    body = res.json()
    # New error envelope: {"error": {"code": ..., "message": ...}}
    assert "Insufficient" in body["error"]["message"]


def test_paginated_items(client, admin_auth, db_session):
    for i in range(25):
        _create_item(db_session, sku=f"WG-T-{i:03d}", name=f"Item {i}")

    res = client.get(
        "/api/inventory/items?page=2&size=10", headers=admin_auth["headers"]
    )
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == 2
    assert body["size"] == 10
    assert len(body["items"]) == 10
    assert body["total"] == 25
    assert body["pages"] == 3


def test_ledger_chain_appended_on_movement(client, admin_auth, db_session):
    """Stock movements should automatically append to the hash-chain ledger."""
    item = _create_item(db_session)
    client.post(
        "/api/inventory/movements",
        headers=admin_auth["headers"],
        json={"item_id": item.id, "type": "outbound", "quantity": 5},
    )
    res = client.get("/api/ledger/verify", headers=admin_auth["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is True
    assert body["entries"] >= 1
