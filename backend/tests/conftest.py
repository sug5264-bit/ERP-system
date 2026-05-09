"""Test fixtures.

Each test gets a fresh in-memory SQLite DB so tests are isolated and fast.
We override the `get_db` dependency to use the test session.
"""
import os

# Force a clean test environment BEFORE app imports.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTO_CREATE_TABLES", "true")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("JWT_SECRET", "test-secret-with-enough-length-for-prod-check-xx")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import models so metadata is populated.
    from app.main import MODULES
    from importlib import import_module
    for m in MODULES:
        import_module(f"app.modules.{m}.models")

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Middleware (audit, scheduler) uses app.core.db.SessionLocal directly —
    # repoint it at the test engine so its writes land in the same in-memory
    # DB the test fixture inspects.
    import app.core.db as _db_mod
    monkeypatch.setattr(_db_mod, "SessionLocal", TestSession)
    # Some modules import SessionLocal at module load time; patch their
    # references too.
    import app.core.audit_middleware as _audit_mw
    monkeypatch.setattr(_audit_mw, "SessionLocal", TestSession)

    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_test_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    u = User(
        email="admin@test.com",
        full_name="Admin",
        hashed_password=hash_password("test1234"),
        role=Role.admin,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def staff_user(db_session):
    from app.core.security import hash_password
    from app.modules.auth.models import Role, User

    u = User(
        email="staff@test.com",
        full_name="Staff",
        hashed_password=hash_password("test1234"),
        role=Role.staff,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def login_as(client, email: str, password: str = "test1234") -> dict:
    res = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    return {
        "access": data["access_token"],
        "refresh": data["refresh_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest.fixture
def admin_auth(client, admin_user):
    return login_as(client, "admin@test.com")


@pytest.fixture
def staff_auth(client, staff_user):
    return login_as(client, "staff@test.com")
