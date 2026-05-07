def test_create_template_with_schema(client, admin_auth):
    res = client.post(
        "/api/approvals/templates",
        headers=admin_auth["headers"],
        json={
            "code": "EXP-T",
            "name": "지출 결의서",
            "description": "비용",
            "schema": [
                {"key": "amount", "label": "금액", "type": "number", "required": True},
                {
                    "key": "category",
                    "label": "분류",
                    "type": "select",
                    "options": ["식대", "교통", "기타"],
                    "required": False,
                },
            ],
            "default_steps": [{"order": 1, "approver_id": 1}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["schema_"]) == 2
    assert body["schema_"][1]["options"] == ["식대", "교통", "기타"]


def test_template_code_unique(client, admin_auth):
    payload = {
        "code": "DUP",
        "name": "Dup",
        "schema": [],
        "default_steps": [],
    }
    a = client.post(
        "/api/approvals/templates", headers=admin_auth["headers"], json=payload
    )
    assert a.status_code == 200
    b = client.post(
        "/api/approvals/templates", headers=admin_auth["headers"], json=payload
    )
    assert b.status_code == 400


def test_form_data_round_trips(client, admin_auth, db_session):
    """Submit an approval with form_data → list it back → form_data is decoded."""
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    approver = User(
        email="approver@test.com",
        full_name="A",
        hashed_password=hash_password("test1234"),
        role=Role.manager,
    )
    db_session.add(approver)
    db_session.commit()
    db_session.refresh(approver)

    res = client.post(
        "/api/approvals",
        headers=admin_auth["headers"],
        json={
            "title": "expense report",
            "resource_type": "expense",
            "resource_id": 0,
            "steps": [{"order": 1, "approver_id": approver.id}],
            "form_data": {"amount": 50000, "category": "식대", "memo": "팀 회식"},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["form_data"] == {"amount": 50000, "category": "식대", "memo": "팀 회식"}

    listed = client.get("/api/approvals?scope=mine", headers=admin_auth["headers"]).json()
    assert listed[0]["form_data"]["amount"] == 50000
