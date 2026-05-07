"""Regression tests for the hardening pass:
   SQL-injection guard on restore, MIME magic check, streaming upload,
   orphan-file cleanup, schema-version refusal, inline PDF preview.
"""
import json
from decimal import Decimal


# --- restore: SQL injection guard ------------------------------------------


def test_restore_strips_unknown_columns(client, admin_auth):
    """Unknown / malicious column keys must be silently dropped, not interpolated."""
    payload = {
        "schema_version": None,
        "tables": {
            "users": [
                {
                    "id": 9999,
                    "email": "evil@test.com",
                    "full_name": "Evil",
                    "hashed_password": "x",
                    "is_active": True,
                    "role": "viewer",
                    # Injection attempt — must be ignored, not concatenated into SQL.
                    "id, email) VALUES (1, 'pwned'); DROP TABLE users; --": "x",
                }
            ]
        },
    }
    files = {
        "file": ("evil.json", json.dumps(payload).encode("utf-8"), "application/json")
    }
    res = client.post(
        "/api/admin/restore?truncate_first=false",
        headers=admin_auth["headers"],
        files=files,
    )
    assert res.status_code == 200
    # users table is still intact (admin login still works after this call)
    me = client.get("/api/auth/me", headers=admin_auth["headers"])
    assert me.status_code == 200


def test_restore_refuses_redacted_backup(client, admin_auth):
    payload = {"redacted": True, "tables": {}}
    files = {
        "file": ("redacted.json", json.dumps(payload).encode("utf-8"), "application/json")
    }
    res = client.post(
        "/api/admin/restore",
        headers=admin_auth["headers"],
        files=files,
    )
    assert res.status_code == 400
    assert "redacted" in res.json()["error"]["message"].lower()


# --- backup: schema_version round-trip ------------------------------------


def test_backup_includes_schema_version(client, admin_auth):
    res = client.get("/api/admin/backup", headers=admin_auth["headers"])
    body = res.json()
    assert "schema_version" in body


# --- attachment: MIME magic check ------------------------------------------


def test_attachment_rejects_extension_content_mismatch(client, admin_auth):
    """A .png file containing PE/ELF/text bytes must be rejected."""
    # Real PNG starts with \x89PNG\r\n\x1a\n. We send something else.
    files = {"file": ("fake.png", b"NOT-A-REAL-PNG", "image/png")}
    res = client.post("/api/attachments", headers=admin_auth["headers"], files=files)
    assert res.status_code == 415
    assert "signature" in res.json()["error"]["message"].lower()


def test_attachment_accepts_valid_png(client, admin_auth):
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    files = {"file": ("real.png", png_header, "image/png")}
    res = client.post("/api/attachments", headers=admin_auth["headers"], files=files)
    assert res.status_code == 200
    assert res.json()["filename"] == "real.png"


# --- attachment: oversize stream is cut off, file is removed ----------------


def test_attachment_oversize_cleans_up(client, admin_auth, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_max_bytes", 100)
    big = b"x" * 500
    files = {"file": ("toobig.txt", big, "text/plain")}
    res = client.post("/api/attachments", headers=admin_auth["headers"], files=files)
    assert res.status_code == 413
    # Confirm no attachment row was created
    listed = client.get("/api/attachments", headers=admin_auth["headers"])
    assert all(a["filename"] != "toobig.txt" for a in listed.json())


# --- streaming CSV --------------------------------------------------------


def test_csv_export_streams(client, admin_auth, db_session):
    from app.modules.inventory.models import Item

    for i in range(20):
        db_session.add(
            Item(sku=f"S-{i:03d}", name=f"품목 {i}", unit="EA", unit_price=Decimal("1"), stock_qty=Decimal("0"))
        )
    db_session.commit()

    res = client.get(
        "/api/inventory/items/export?format=csv", headers=admin_auth["headers"]
    )
    assert res.status_code == 200
    body = res.content.decode("utf-8-sig")
    # All 20 items present in the streamed output
    for i in range(20):
        assert f"S-{i:03d}" in body


# --- inline PDF preview ----------------------------------------------------


def test_pdf_export_inline_disposition(client, admin_auth):
    res = client.get(
        "/api/inventory/items/export?format=pdf&inline=true",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    cd = res.headers["content-disposition"]
    assert cd.lower().startswith("inline;")


def test_pdf_export_default_attachment(client, admin_auth):
    res = client.get(
        "/api/inventory/items/export?format=pdf",
        headers=admin_auth["headers"],
    )
    cd = res.headers["content-disposition"]
    assert cd.lower().startswith("attachment;")
