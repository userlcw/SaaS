"""登录接口单元测试。

运行：
    cd python
    pytest backend/tests -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证可以 import backend.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 使用独立测试数据库
os.environ["DATABASE_URL"] = "sqlite:///./test_login.db"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core.security import hash_password  # noqa: E402
from backend.app.db.init_db import init_db  # noqa: E402
from backend.app.db.session import SessionLocal, engine  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models.user import User  # noqa: E402
from backend.config import settings  # noqa: E402


def _reset_db() -> None:
    from backend.app.db.session import Base

    Base.metadata.drop_all(bind=engine)
    init_db()


def _make_user(username: str = "alice", password: str = "Pass@1234") -> None:
    with SessionLocal() as db:
        u = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(u)
        db.commit()


def test_login_success():
    _reset_db()
    _make_user()
    client = TestClient(app)
    r = client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "alice", "password": "Pass@1234"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["token"]["access_token"]


def test_login_wrong_password():
    _reset_db()
    _make_user()
    client = TestClient(app)
    r = client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "alice", "password": "WrongPass1"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40101


def test_me_requires_token():
    client = TestClient(app)
    r = client.get(f"{settings.api_v1_prefix}/auth/me")
    assert r.status_code == 401


def test_me_with_token():
    _reset_db()
    _make_user()
    client = TestClient(app)
    r = client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "alice", "password": "Pass@1234"},
    )
    token = r.json()["data"]["token"]["access_token"]
    r2 = client.get(
        f"{settings.api_v1_prefix}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["username"] == "alice"


def test_refresh_flow_sets_cookie():
    """登录成功应下发 refresh_token cookie，/refresh 可换新 access_token。"""
    _reset_db()
    _make_user()
    client = TestClient(app)
    r = client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "alice", "password": "Pass@1234"},
    )
    assert r.status_code == 200
    # cookie 已下发
    assert settings.refresh_cookie_name in r.cookies

    r2 = client.post(f"{settings.api_v1_prefix}/auth/refresh")
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["token"]["access_token"]


def test_refresh_requires_cookie():
    client = TestClient(app)
    client.cookies.clear()
    r = client.post(f"{settings.api_v1_prefix}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == 40104


def test_ip_rate_limit_triggers_429():
    """在 IP 限流窗口内连续失败到达上限后应返回 429。"""
    _reset_db()
    _make_user()
    # 使 IP 限流阈值可控地被触发
    from backend.app.core.rate_limit import ip_limiter
    ip_limiter._max = 3
    ip_limiter._events.clear()
    ip_limiter._blocked_until.clear()

    client = TestClient(app)
    for _ in range(3):
        client.post(
            f"{settings.api_v1_prefix}/auth/login",
            json={"username": "alice", "password": "wrong-pass-1"},
        )
    r = client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "alice", "password": "wrong-pass-2"},
    )
    assert r.status_code == 429
    assert r.json()["code"] in (42901, 42902)
