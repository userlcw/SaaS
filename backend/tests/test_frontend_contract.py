from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend" / "public"


def test_containers_page_contract():
    html = (PUBLIC / "containers.html").read_text(encoding="utf-8")

    assert 'id="containerTableBody"' in html
    assert 'id="createContainerModal"' in html
    assert 'id="imageListBody"' in html
    assert html.index('id="imageListBody"') < html.index('id="containerTableBody"')
    assert html.index('id="pageSize"') > html.index('id="containerTableBody"')
    assert 'id="containerLogModal"' in html
    assert 'id="containerLogContent"' in html
    assert "/static/js/containers.js?v=" in html


def test_login_redirects_to_container_console_without_debug_panel():
    html = (PUBLIC / "index.html").read_text(encoding="utf-8")
    js = (PUBLIC / "js" / "login.js").read_text(encoding="utf-8")

    assert "userPanel" not in html
    assert "/static/js/login.js?v=" in html
    assert 'window.location.replace("/console")' in js
    assert "JSON.stringify(user, null, 2)" not in js


def test_frontend_uses_unified_console_routes_and_session_token():
    main_py = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    api_js = (PUBLIC / "js" / "api.js").read_text(encoding="utf-8")
    containers_js = (PUBLIC / "js" / "containers.js").read_text(encoding="utf-8")

    assert '@app.get("/console"' in main_py
    assert '@app.get("/console/containers"' in main_py
    assert '@app.get("/console/terminal"' in main_py
    assert 'const TOKEN_KEY = "docker_console_access_token"' in api_js
    assert "sessionStorage.setItem(TOKEN_KEY, token)" in api_js
    assert "sessionStorage.getItem(TOKEN_KEY)" in api_js
    assert 'window.location.replace("/")' in containers_js


def test_api_js_exposes_docker_methods():
    js = (PUBLIC / "js" / "api.js").read_text(encoding="utf-8")

    for method in [
        "listContainers",
        "listImages",
        "createContainer",
        "startContainer",
        "stopContainer",
        "restartContainer",
        "deleteContainer",
        "getContainerLogs",
    ]:
        assert f"{method}(" in js


def test_container_console_renders_server_images_and_custom_controls():
    html = (PUBLIC / "containers.html").read_text(encoding="utf-8")
    js = (PUBLIC / "js" / "containers.js").read_text(encoding="utf-8")
    css = (PUBLIC / "css" / "login.css").read_text(encoding="utf-8")

    assert "服务器镜像" in html
    assert "renderImageList" in js
    assert "formatBytes" in js
    assert "state.images.map" in js
    assert "image-list" in css
    assert "select option" in css
    assert "appearance: none" in css
    assert "input[type=\"number\"]::-webkit-inner-spin-button" in css
    assert ".toggle-line input[type=\"checkbox\"]" in css


def test_container_console_has_log_and_terminal_actions():
    js = (PUBLIC / "js" / "containers.js").read_text(encoding="utf-8")
    terminal_html = (PUBLIC / "terminal.html").read_text(encoding="utf-8")
    terminal_js = (PUBLIC / "js" / "terminal.js").read_text(encoding="utf-8")

    assert 'data-action="logs"' in js
    assert 'data-action="terminal"' in js
    assert "openLogModal" in js
    assert "openTerminalPage" in js
    assert "containerTerminal" in terminal_html
    assert "new WebSocket" in terminal_js
    assert "/api/v1/containers/" in terminal_js


def test_console_has_collapsible_sidebar_and_lazy_views():
    html = (PUBLIC / "containers.html").read_text(encoding="utf-8")
    js = (PUBLIC / "js" / "containers.js").read_text(encoding="utf-8")
    api_js = (PUBLIC / "js" / "api.js").read_text(encoding="utf-8")

    assert 'id="appSidebar"' in html
    assert 'id="sidebarToggle"' in html
    assert 'data-view="containers"' in html
    assert 'data-view="dashboard"' in html
    assert 'data-view="users"' in html
    assert 'id="dashboardView"' in html
    assert 'id="usersView"' in html
    assert "docker_console_sidebar_collapsed" in js
    assert "activateView" in js
    assert "loadDashboard" in js
    assert "loadUsers" in js
    assert "loadAuditLogs" in js
    assert "getDashboardMetrics" in api_js
    assert "listUsers" in api_js
    assert "listAuditLogs" in api_js
