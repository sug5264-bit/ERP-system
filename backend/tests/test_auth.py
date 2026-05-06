def test_login_returns_token_pair(client, admin_user):
    res = client.post(
        "/api/auth/login",
        data={"username": "admin@test.com", "password": "test1234"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password(client, admin_user):
    res = client.post(
        "/api/auth/login",
        data={"username": "admin@test.com", "password": "wrong"},
    )
    assert res.status_code == 401


def test_refresh_rotates_token(client, admin_auth):
    res = client.post("/api/auth/refresh", json={"refresh_token": admin_auth["refresh"]})
    assert res.status_code == 200
    new_refresh = res.json()["refresh_token"]
    assert new_refresh != admin_auth["refresh"]

    # Old refresh is now revoked.
    res2 = client.post("/api/auth/refresh", json={"refresh_token": admin_auth["refresh"]})
    assert res2.status_code == 401


def test_logout_revokes_refresh(client, admin_auth):
    res = client.post("/api/auth/logout", json={"refresh_token": admin_auth["refresh"]})
    assert res.status_code == 200
    res2 = client.post("/api/auth/refresh", json={"refresh_token": admin_auth["refresh"]})
    assert res2.status_code == 401


def test_me_endpoint(client, admin_auth):
    res = client.get("/api/auth/me", headers=admin_auth["headers"])
    assert res.status_code == 200
    assert res.json()["email"] == "admin@test.com"


def test_unauthenticated_blocked(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
