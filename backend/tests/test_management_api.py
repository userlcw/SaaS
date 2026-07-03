from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.v1 import admin as admin_api
from backend.app.api.v1 import containers as containers_api
from backend.app.db.session import Base, get_db
from backend.app.main import app
from backend.app.models.docker import AuditLog
from backend.app.models.rbac import Permission, Role, RolePermission, UserRole
from backend.app.models.user import User


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'management.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_auth(is_admin: bool = True):
    return {"id": 1, "username": "admin", "is_admin": is_admin}


def test_dashboard_metrics_returns_cached_resource_snapshot():
    client = TestClient(app)
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth(True)

    resp = client.get("/api/v1/dashboard/metrics")

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"cpu", "memory", "disk", "network", "sampled_at", "cache_ttl_seconds"}.issubset(data)
    assert isinstance(data["cpu"]["percent"], (int, float))
    app.dependency_overrides.clear()


def test_users_endpoint_returns_roles_and_permissions(tmp_path):
    Session = _session(tmp_path)
    with Session() as db:
        user = User(username="operator", email="operator@example.com", password_hash="hash", is_active=True)
        role = Role(name="ops", description="运维")
        perm = Permission(code="container:view", description="查看容器")
        db.add_all([user, role, perm])
        db.flush()
        db.add_all([UserRole(user_id=user.id, role_id=role.id), RolePermission(role_id=role.id, permission_id=perm.id)])
        db.commit()

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[admin_api.get_current_user_for_admin] = lambda: _override_auth(True)
    client = TestClient(app)

    resp = client.get("/api/v1/users?keyword=oper&sort=username")

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["username"] == "operator"
    assert item["roles"] == ["ops"]
    assert item["permissions"] == ["container:view"]
    app.dependency_overrides.clear()


def test_audit_logs_endpoint_filters_by_user_and_action(tmp_path):
    Session = _session(tmp_path)
    with Session() as db:
        user = User(username="operator", email="operator@example.com", password_hash="hash", is_active=True)
        db.add(user)
        db.flush()
        db.add(
            AuditLog(
                user_id=user.id,
                ip="127.0.0.1",
                action="container:start",
                result="success",
                params_summary='{"before": "exited", "after": "running"}',
                created_at=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
            )
        )
        db.commit()

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[admin_api.get_current_user_for_admin] = lambda: _override_auth(True)
    client = TestClient(app)

    resp = client.get("/api/v1/audit-logs?user=operator&action=container:start")

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["username"] == "operator"
    assert item["action"] == "container:start"
    assert item["ip"] == "127.0.0.1"
    app.dependency_overrides.clear()
