from __future__ import annotations

from backend.app.services.docker_service import (
    DockerListFilters,
    detect_container_type,
    format_ports,
    paginate_items,
    parse_container_summary,
    parse_image_summary,
)


class _FakeImage:
    id = "sha256:abcdef1234567890"
    tags = ["nginx:1.25", "nginx:latest"]

    attrs = {
        "Created": "2026-07-01T12:00:00Z",
        "Size": 123456789,
        "Config": {"Labels": {"org.opencontainers.image.title": "Nginx"}},
    }


class _FakeContainer:
    id = "1234567890abcdef"
    name = "web-nginx"
    image = _FakeImage()
    status = "running"
    attrs = {
        "Created": "2026-07-01T12:10:00Z",
        "State": {"Status": "running", "StartedAt": "2026-07-01T12:11:00Z", "Health": {"Status": "healthy"}},
        "Config": {"Image": "nginx:1.25", "Labels": {"console.channel": "prod"}},
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
                "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}],
                "53/udp": None,
            }
        },
    }

    def logs(self, tail=200, timestamps=True):
        assert tail == 50
        assert timestamps is True
        return b"2026-07-02T10:00:00Z boot ok\n2026-07-02T10:01:00Z serving\n"


def test_format_ports_includes_host_ip_port_container_port_and_protocol():
    ports = format_ports(_FakeContainer.attrs["NetworkSettings"]["Ports"])

    assert "0.0.0.0:8080 -> 80/tcp" in ports
    assert "127.0.0.1:8443 -> 443/tcp" in ports
    assert "53/udp" in ports


def test_detect_container_type_from_image_name():
    assert detect_container_type("redis:7") == "redis"
    assert detect_container_type("library/mysql:8.0") == "mysql"
    assert detect_container_type("custom/unknown:latest") == "other"


def test_parse_container_summary_normalizes_fields():
    item = parse_container_summary(_FakeContainer(), server_name="local", server_ip="127.0.0.1")

    assert item["id"] == "1234567890ab"
    assert item["name"] == "web-nginx"
    assert item["server_ip"] == "127.0.0.1"
    assert item["container_type"] == "nginx"
    assert item["image"] == "nginx:1.25"
    assert item["status"] == "running"
    assert item["health"] == "healthy"
    assert item["channel"] == "prod"
    assert "0.0.0.0:8080 -> 80/tcp" in item["ports"]


def test_parse_image_summary_uses_first_tag_and_size():
    item = parse_image_summary(_FakeImage())

    assert item["id"] == "abcdef123456"
    assert item["repository"] == "nginx"
    assert item["tag"] == "1.25"
    assert item["name"] == "nginx:1.25"
    assert item["image_type"] == "nginx"
    assert item["size"] == 123456789


def test_paginate_items_filters_keyword_status_and_image():
    items = [
        {"name": "web-nginx", "image": "nginx:1.25", "status": "running", "server_ip": "10.0.0.1", "ports": ["8080 -> 80/tcp"]},
        {"name": "cache-redis", "image": "redis:7", "status": "exited", "server_ip": "10.0.0.1", "ports": ["6379/tcp"]},
        {"name": "db-mysql", "image": "mysql:8", "status": "running", "server_ip": "10.0.0.2", "ports": ["3306/tcp"]},
    ]
    filters = DockerListFilters(keyword="nginx", status="running", image="nginx", page=1, page_size=10)

    page = paginate_items(items, filters)

    assert page["total"] == 1
    assert page["items"][0]["name"] == "web-nginx"


def test_container_logs_decodes_docker_log_bytes():
    class _FakeContainers:
        def get(self, container_id):
            assert container_id == "abc123"
            return _FakeContainer()

    class _FakeClient:
        containers = _FakeContainers()

    from backend.app.services.docker_service import DockerService

    text = DockerService(client=_FakeClient()).container_logs("abc123", tail=50)

    assert "boot ok" in text
    assert "serving" in text
