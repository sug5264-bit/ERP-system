def test_health_basic(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_detailed_db_ok(client):
    res = client.get("/api/health/detailed")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True


def test_pagination_envelope_shape(client, admin_auth):
    res = client.get("/api/sales/customers?page=1&size=5", headers=admin_auth["headers"])
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"items", "total", "page", "size", "pages"}
    assert body["page"] == 1
    assert body["size"] == 5
    assert isinstance(body["items"], list)


def test_size_clamped(client, admin_auth):
    """size has a max of 200; 9999 should fail validation."""
    res = client.get("/api/sales/customers?page=1&size=9999", headers=admin_auth["headers"])
    assert res.status_code == 422
