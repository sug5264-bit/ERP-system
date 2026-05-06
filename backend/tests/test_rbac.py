def test_staff_cannot_create_finance_account(client, staff_auth):
    res = client.post(
        "/api/finance/accounts",
        headers=staff_auth["headers"],
        json={"code": "9999", "name": "Test", "type": "expense"},
    )
    assert res.status_code == 403


def test_admin_can_create_finance_account(client, admin_auth):
    res = client.post(
        "/api/finance/accounts",
        headers=admin_auth["headers"],
        json={"code": "9999", "name": "Test", "type": "expense"},
    )
    assert res.status_code == 200


def test_module_permission_override(client, admin_auth, db_session):
    """Per-module permission lets a staff user act as manager in finance."""
    from app.modules.auth.models import Role, User, UserModulePermission

    staff = User(
        email="override@test.com",
        full_name="O",
        hashed_password="$2b$12$x" + "x" * 50,
        role=Role.staff,
    )
    db_session.add(staff)
    db_session.commit()
    db_session.refresh(staff)

    # admin sets staff to manager on finance
    res = client.put(
        f"/api/auth/users/{staff.id}/permissions",
        headers=admin_auth["headers"],
        json=[{"module": "finance", "role": "manager"}],
    )
    assert res.status_code == 200

    # Verify the perm row exists
    perm = (
        db_session.query(UserModulePermission)
        .filter(UserModulePermission.user_id == staff.id)
        .first()
    )
    assert perm is not None
    assert perm.module == "finance"
    assert perm.role == Role.manager
