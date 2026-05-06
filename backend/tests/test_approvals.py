def test_approval_chain_two_steps(client, admin_auth, db_session):
    """staff requests; manager approves step 1; admin approves step 2 → final."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    staff = User(
        email="staff2@test.com",
        full_name="S",
        hashed_password=hash_password("test1234"),
        role=Role.staff,
    )
    manager = User(
        email="mgr@test.com",
        full_name="M",
        hashed_password=hash_password("test1234"),
        role=Role.manager,
    )
    db_session.add_all([staff, manager])
    db_session.commit()
    db_session.refresh(staff)
    db_session.refresh(manager)

    # staff submits
    staff_login = client.post(
        "/api/auth/login",
        data={"username": "staff2@test.com", "password": "test1234"},
    ).json()
    staff_h = {"Authorization": f"Bearer {staff_login['access_token']}"}

    res = client.post(
        "/api/approvals",
        headers=staff_h,
        json={
            "title": "Test",
            "resource_type": "sales_order",
            "resource_id": 1,
            "steps": [
                {"order": 1, "approver_id": manager.id},
                {"order": 2, "approver_id": 1},  # admin (id=1)
            ],
        },
    )
    assert res.status_code == 200
    req_id = res.json()["id"]

    # staff cannot approve (not assigned)
    res = client.post(
        f"/api/approvals/{req_id}/approve",
        headers=staff_h,
        json={"comment": "hi"},
    )
    assert res.status_code == 400

    # manager approves step 1
    mgr_login = client.post(
        "/api/auth/login",
        data={"username": "mgr@test.com", "password": "test1234"},
    ).json()
    mgr_h = {"Authorization": f"Bearer {mgr_login['access_token']}"}
    res = client.post(
        f"/api/approvals/{req_id}/approve",
        headers=mgr_h,
        json={"comment": "ok"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending"
    assert res.json()["current_step"] == 2

    # admin approves step 2 → final
    res = client.post(
        f"/api/approvals/{req_id}/approve",
        headers=admin_auth["headers"],
        json={"comment": "final"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
