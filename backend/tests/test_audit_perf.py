"""Verify the audit middleware doesn't choke on uploads or huge bodies."""
from io import BytesIO


def test_audit_skips_body_for_attachment_upload(client, admin_auth, db_session):
    """Attachment upload must NOT have its raw bytes copied into the audit row."""
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024  # 1 KB-ish
    files = {"file": ("perf.png", png_header, "image/png")}
    res = client.post("/api/attachments", headers=admin_auth["headers"], files=files)
    assert res.status_code == 200

    from app.modules.audit.models import AuditLog

    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.path == "/api/attachments")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert row is not None
    # Audit captured the request, but explicitly DIDN'T inline the binary body.
    assert row.payload == "(body skipped — large/binary payload)"


def test_audit_truncates_huge_body(client, admin_auth, db_session):
    """If a write endpoint receives a giant JSON body, audit row stays small."""
    from app.modules.audit.models import AuditLog

    huge = {"data": "x" * 200_000}  # 200 KB
    # /api/edi/inbound is a normal JSON write — audit captures it, but truncated.
    client.post(
        "/api/edi/inbound",
        headers=admin_auth["headers"],
        json={"msg_type": "CUSTOM", "payload": huge},
    )
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.path == "/api/edi/inbound")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert row is not None
    # 4 KB cap means we never write the 200 KB body
    assert row.payload is not None
    assert len(row.payload) <= 4_100  # MAX_PAYLOAD with a little slack


def test_backup_streams_valid_json(client, admin_auth, db_session):
    """Streaming form must still produce valid, parsable JSON."""
    import json as _json

    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    # Add some rows so multiple tables are non-empty
    db_session.add(
        User(
            email="bk@test.com",
            full_name="BK",
            hashed_password=hash_password("test1234"),
            role=Role.staff,
        )
    )
    db_session.commit()

    res = client.get("/api/admin/backup", headers=admin_auth["headers"])
    assert res.status_code == 200
    parsed = _json.loads(res.content.decode("utf-8"))
    assert "tables" in parsed
    assert "schema_version" in parsed
    assert isinstance(parsed["tables"], dict)
    # Users table is present and contains the row we just inserted
    emails = [u.get("email") for u in parsed["tables"].get("users", [])]
    assert "bk@test.com" in emails


def test_pager_uses_passed_size_in_label():
    """Pager should compute the 'showing X-Y' label from the size it was given,
    not a hardcoded 20."""
    from pathlib import Path

    src = Path("components/Pager.tsx").read_text() if Path("components/Pager.tsx").exists() else ""
    if not src:
        # Reading from frontend dir from backend test — best-effort path
        src = Path("../frontend/components/Pager.tsx").read_text()
    # No literal '* 20 + 1' or 'page * 20' (those were the bug)
    assert "* 20 + 1" not in src
    assert "page * 20" not in src
