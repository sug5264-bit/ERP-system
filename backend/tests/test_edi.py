from decimal import Decimal


def _create_item(db_session, sku):
    from app.modules.inventory.models import Item

    item = Item(
        sku=sku, name=sku, unit="EA", unit_price=Decimal("1000"), stock_qty=Decimal("0")
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_inbound_po_creates_sales_order(client, admin_auth, db_session):
    _create_item(db_session, "WG-EDI-1")

    res = client.post(
        "/api/edi/inbound",
        headers=admin_auth["headers"],
        json={
            "msg_type": "PO",
            "partner_code": "PARTNER-A",
            "payload": {
                "customer_code": "PARTNER-A",
                "customer_name": "Partner A",
                "order_no": "EDI-T-001",
                "items": [{"sku": "WG-EDI-1", "qty": 5, "unit_price": 1000}],
            },
        },
    )
    assert res.status_code == 200
    msg_id = res.json()["id"]

    res = client.post(
        f"/api/edi/messages/{msg_id}/process", headers=admin_auth["headers"]
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "processed"
    assert body["related_resource_type"] == "sales_order"

    # Sales order really exists
    from app.modules.sales.models import SalesOrder

    so = (
        db_session.query(SalesOrder)
        .filter(SalesOrder.id == body["related_resource_id"])
        .first()
    )
    assert so is not None
    assert so.order_no == "EDI-T-001"


def test_inbound_idempotent_reprocess(client, admin_auth, db_session):
    """Processing the same message twice should not create two SalesOrders."""
    _create_item(db_session, "WG-EDI-2")

    res = client.post(
        "/api/edi/inbound",
        headers=admin_auth["headers"],
        json={
            "msg_type": "PO",
            "payload": {
                "customer_name": "P-B",
                "order_no": "EDI-T-002",
                "items": [{"sku": "WG-EDI-2", "qty": 1, "unit_price": 100}],
            },
        },
    )
    msg_id = res.json()["id"]

    client.post(f"/api/edi/messages/{msg_id}/process", headers=admin_auth["headers"])
    client.post(f"/api/edi/messages/{msg_id}/process", headers=admin_auth["headers"])

    from app.modules.sales.models import SalesOrder

    count = (
        db_session.query(SalesOrder).filter(SalesOrder.order_no == "EDI-T-002").count()
    )
    assert count == 1


def test_inbound_unknown_sku_fails_cleanly(client, admin_auth, db_session):
    """Unknown SKU should fail and NOT leave a partial Customer behind."""
    res = client.post(
        "/api/edi/inbound",
        headers=admin_auth["headers"],
        json={
            "msg_type": "PO",
            "payload": {
                "customer_name": "PartialCustomer",
                "order_no": "EDI-T-FAIL",
                "items": [{"sku": "DOES-NOT-EXIST", "qty": 1, "unit_price": 100}],
            },
        },
    )
    msg_id = res.json()["id"]

    r = client.post(
        f"/api/edi/messages/{msg_id}/process", headers=admin_auth["headers"]
    )
    assert r.status_code == 400

    # Customer should NOT have been created (savepoint rolled back)
    from app.modules.sales.models import Customer

    rows = (
        db_session.query(Customer).filter(Customer.name == "PartialCustomer").count()
    )
    assert rows == 0


def test_outbound_invoice_for_confirmed_order(client, admin_auth, db_session):
    item = _create_item(db_session, "WG-EDI-3")

    # set up a confirmed sales order
    from app.modules.inventory.models import Item
    item = db_session.query(Item).filter(Item.sku == "WG-EDI-3").first()
    item.stock_qty = Decimal("100")
    db_session.commit()

    cust_res = client.post(
        "/api/sales/customers",
        headers=admin_auth["headers"],
        json={"name": "Cust EDI"},
    )
    cust_id = cust_res.json()["id"]

    so_res = client.post(
        "/api/sales/orders",
        headers=admin_auth["headers"],
        json={
            "order_no": "SO-EDI-1",
            "customer_id": cust_id,
            "items": [{"item_id": item.id, "quantity": 1, "unit_price": 1000}],
        },
    )
    so_id = so_res.json()["id"]

    confirm = client.post(
        f"/api/sales/orders/{so_id}/confirm", headers=admin_auth["headers"]
    )
    assert confirm.status_code == 200

    # Now emit invoice
    r = client.post(
        f"/api/edi/outbound/invoice/{so_id}", headers=admin_auth["headers"]
    )
    assert r.status_code == 200
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["msg_type"] == "INVOIC"
    assert body["status"] == "sent"
