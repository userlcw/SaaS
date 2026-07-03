from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient

from backend.app.api.v1 import containers as containers_api
from backend.app.db.session import get_db
from backend.app.models.docker import AuditLog
from backend.app.main import app


class _FakeDockerService:
    def list_containers(self, filters):
        return {
            "items": [
                {
                    "id": "abc123",
                    "name": "web-nginx",
                    "server_name": "local",
                    "server_ip": "127.0.0.1",
                    "container_type": "nginx",
                    "image": "nginx:latest",
                    "status": "running",
                    "health": "healthy",
                    "ports": ["0.0.0.0:8080 -> 80/tcp"],
                    "created_at": "2026-07-01T12:00:00Z",
                    "started_at": "2026-07-01T12:00:10Z",
                    "channel": "prod",
                }
            ],
            "total": 1,
            "page": filters.page,
            "page_size": filters.page_size,
            "pages": 1,
        }

    def list_images(self, server: str = "local"):
        return [
            {
                "id": "img123",
                "name": "nginx:latest",
                "repository": "nginx",
                "tag": "latest",
                "image_type": "nginx",
                "size": 123,
                "created_at": "2026-07-01T12:00:00Z",
            }
        ]

    def create_container(self, payload):
        return {"id": "new123", "name": payload.name, "status": "created"}

    def container_summary(self, container_id: str):
        return {"id": container_id[:12], "docker_id": container_id, "name": "web-nginx", "status": "exited"}

    def start_container(self, container_id: str):
        return {"id": container_id[:12], "docker_id": container_id, "name": "web-nginx", "status": "running"}

    def container_logs(self, container_id: str, tail: int = 200):
        return f"{container_id}: boot ok"


def _override_auth(is_admin: bool = True):
    return {
        "id": 1,
        "username": "admin" if is_admin else "user",
        "is_admin": is_admin,
    }


def test_list_containers_returns_paginated_response():
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth()
    client = TestClient(app)

    resp = client.get("/api/v1/containers?keyword=nginx&page=1&page_size=20")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["name"] == "web-nginx"
    app.dependency_overrides.clear()


def test_list_images_returns_available_server_images():
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth()
    client = TestClient(app)

    resp = client.get("/api/v1/images?server=local")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["items"][0]["name"] == "nginx:latest"
    app.dependency_overrides.clear()


def test_create_container_requires_admin_user():
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth(False)
    client = TestClient(app)

    resp = client.post("/api/v1/containers", json={"server": "local", "image": "nginx:latest", "name": "demo"})

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["code"] == 40301
    app.dependency_overrides.clear()


def test_create_container_returns_created_summary_for_admin():
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth(True)
    client = TestClient(app)

    resp = client.post("/api/v1/containers", json={"server": "local", "image": "nginx:latest", "name": "demo"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["name"] == "demo"
    app.dependency_overrides.clear()


def test_container_logs_returns_tail_text_for_admin():
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth(True)
    client = TestClient(app)

    resp = client.get("/api/v1/containers/abc123/logs?tail=50")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["container_id"] == "abc123"
    assert body["data"]["logs"] == "abc123: boot ok"
    app.dependency_overrides.clear()


def test_container_action_records_audit_log(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.db.session import Base
    from backend.app.models import docker as docker_models  # noqa: F401
    from backend.app.models import rbac as rbac_models  # noqa: F401
    from backend.app.models import user as user_models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
      db = Session()
      try:
          yield db
      finally:
          db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[containers_api.get_docker_service] = lambda: _FakeDockerService()
    app.dependency_overrides[containers_api.get_current_user_for_docker] = lambda: _override_auth(True)
    client = TestClient(app)

    resp = client.post("/api/v1/containers/abc123/actions/start")

    assert resp.status_code == 200, resp.text
    with Session() as db:
        log = db.query(AuditLog).one()
        assert log.action == "container:start"
        assert log.result == "success"
        assert "before" in log.params_summary
        assert "after" in log.params_summary
    app.dependency_overrides.clear()
