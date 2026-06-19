"""create_admin 스크립트 동작 검증."""
import os
import sys


def test_strong_password_rules():
    from scripts.create_admin import _strong_password

    ok, _ = _strong_password("Abcdefgh1!23")
    assert ok is True

    cases = [
        ("short", "12자"),
        ("alllowercase1!ab", "대문자"),
        ("ALLUPPERCASE1!AB", "소문자"),
        ("NoDigitsAbcde!@", "숫자"),
        ("NoSpecialAbc1234", "특수문자"),
    ]
    for pw, expected_word in cases:
        ok, reason = _strong_password(pw)
        assert ok is False
        assert expected_word in reason


def test_generated_password_is_strong():
    from scripts.create_admin import _generate_password, _strong_password

    for _ in range(20):
        pw = _generate_password()
        ok, reason = _strong_password(pw)
        assert ok, f"생성된 비밀번호가 약함: {pw} ({reason})"
        assert len(pw) == 24


def test_create_and_reset_admin(tmp_path, monkeypatch):
    """end-to-end: 신규 생성 → 중복 거부 → --reset 갱신."""
    db_file = tmp_path / "admin_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("JWT_SECRET", "x" * 50)
    monkeypatch.setenv("SEED_DEMO_USERS", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    monkeypatch.setenv("STRONG", "Abcdefgh1!23")

    # 모듈 재로드 (env 캐시 회피)
    for mod in list(sys.modules):
        if mod.startswith("app.") or mod.startswith("scripts.create_admin"):
            sys.modules.pop(mod, None)

    from scripts.create_admin import main

    # 1) 신규 생성
    rc = main([
        "--email", "ops@example.com", "--name", "운영",
        "--password-env", "STRONG",
    ])
    assert rc == 0

    # 2) 중복 거부
    rc = main([
        "--email", "ops@example.com", "--name", "운영",
        "--password-env", "STRONG",
    ])
    assert rc == 1

    # 3) --reset 갱신
    rc = main([
        "--email", "ops@example.com", "--name", "운영_갱신",
        "--password-env", "STRONG", "--reset",
    ])
    assert rc == 0

    # DB 확인
    from app.core.db import SessionLocal
    from app.modules.auth.models import Role, User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "ops@example.com").first()
        assert u is not None
        assert u.role == Role.admin
        assert u.full_name == "운영_갱신"
    finally:
        db.close()


def test_weak_password_via_env_rejected(tmp_path, monkeypatch):
    db_file = tmp_path / "weak.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("JWT_SECRET", "x" * 50)
    monkeypatch.setenv("SEED_DEMO_USERS", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    monkeypatch.setenv("WEAK", "short")

    for mod in list(sys.modules):
        if mod.startswith("app.") or mod.startswith("scripts.create_admin"):
            sys.modules.pop(mod, None)

    from scripts.create_admin import main
    rc = main([
        "--email", "weak@example.com", "--name", "X",
        "--password-env", "WEAK",
    ])
    assert rc == 2
