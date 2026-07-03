"""Docker 容器/镜像数据解析、筛选与轻量服务封装。"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Iterable

from backend.app.schemas.docker import ContainerCreateRequest

COMMON_IMAGE_TYPES = {
    "nginx": "nginx",
    "openresty": "openresty",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "redis": "redis",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mongo": "mongo",
    "rabbitmq": "rabbitmq",
    "elasticsearch": "elasticsearch",
    "kibana": "kibana",
    "prometheus": "prometheus",
    "grafana": "grafana",
    "jenkins": "jenkins",
    "gitlab": "gitlab",
    "minio": "minio",
    "traefik": "traefik",
    "caddy": "caddy",
    "node": "node",
    "python": "python",
    "java": "java",
    "php": "php",
    "golang": "go",
    "go": "go",
}


@dataclass(slots=True)
class DockerListFilters:
    keyword: str = ""
    query_field: str = "all"
    server: str = ""
    status: str = ""
    channel: str = ""
    image: str = ""
    container_type: str = ""
    page: int = 1
    page_size: int = 20
    sort: str = "name"


def detect_container_type(image_name: str, labels: dict[str, Any] | None = None) -> str:
    """按 label 与镜像名识别常见容器类型。"""
    labels = labels or {}
    label_text = " ".join(str(v).lower() for v in labels.values() if v)
    image_text = (image_name or "").lower()
    haystack = f"{label_text} {image_text}"
    for key, value in COMMON_IMAGE_TYPES.items():
        if key in haystack:
            return value
    return "other"


def format_ports(raw_ports: dict[str, Any] | None) -> list[str]:
    """将 Docker ports 字段格式化为 HostIp:HostPort -> ContainerPort/proto。"""
    if not raw_ports:
        return []
    result: list[str] = []
    for container_port, bindings in sorted(raw_ports.items()):
        if not bindings:
            result.append(str(container_port))
            continue
        for binding in bindings:
            host_ip = binding.get("HostIp") or "0.0.0.0"
            host_port = binding.get("HostPort") or ""
            result.append(f"{host_ip}:{host_port} -> {container_port}")
    return result


def _short_id(value: str) -> str:
    value = (value or "").replace("sha256:", "")
    return value[:12]


def _first_image_tag(container_or_image: Any) -> str:
    image = getattr(container_or_image, "image", container_or_image)
    tags = getattr(image, "tags", None) or []
    if tags:
        return tags[0]
    attrs = getattr(container_or_image, "attrs", {}) or {}
    config = attrs.get("Config") or {}
    return config.get("Image") or "<none>:<none>"


def parse_container_summary(container: Any, server_name: str = "local", server_ip: str = "127.0.0.1") -> dict[str, Any]:
    """把 docker SDK Container 对象归一化为前端列表数据。"""
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config") or {}
    labels = config.get("Labels") or {}
    state = attrs.get("State") or {}
    network = attrs.get("NetworkSettings") or {}
    image = config.get("Image") or _first_image_tag(container)
    status = state.get("Status") or getattr(container, "status", "unknown") or "unknown"
    health = (state.get("Health") or {}).get("Status") or ""
    ports = format_ports(network.get("Ports") or {})
    return {
        "id": _short_id(getattr(container, "id", "")),
        "docker_id": getattr(container, "id", ""),
        "name": (getattr(container, "name", "") or "").lstrip("/"),
        "server_name": server_name,
        "server_ip": server_ip,
        "container_type": detect_container_type(image, labels),
        "image": image,
        "status": status,
        "health": health,
        "ports": ports,
        "created_at": attrs.get("Created") or "",
        "started_at": state.get("StartedAt") or "",
        "channel": labels.get("console.channel") or "",
        "labels": labels,
    }


def parse_image_summary(image: Any) -> dict[str, Any]:
    """把 docker SDK Image 对象归一化为镜像选择数据。"""
    attrs = getattr(image, "attrs", {}) or {}
    tags = getattr(image, "tags", None) or []
    name = tags[0] if tags else "<none>:<none>"
    if ":" in name and "/" not in name.rsplit(":", 1)[-1]:
        repository, tag = name.rsplit(":", 1)
    else:
        repository, tag = name, "latest"
    labels = (attrs.get("Config") or {}).get("Labels") or {}
    return {
        "id": _short_id(getattr(image, "id", "")),
        "docker_id": getattr(image, "id", ""),
        "name": name,
        "repository": repository,
        "tag": tag,
        "image_type": detect_container_type(name, labels),
        "size": attrs.get("Size") or 0,
        "created_at": attrs.get("Created") or "",
    }


def _matches_keyword(item: dict[str, Any], keyword: str, query_field: str) -> bool:
    if not keyword:
        return True
    keyword = keyword.lower()
    fields = {
        "name": [item.get("name", "")],
        "image": [item.get("image", "")],
        "port": item.get("ports", []),
        "ip": [item.get("server_ip", "")],
        "id": [item.get("id", ""), item.get("docker_id", "")],
    }
    values: Iterable[Any]
    if query_field in fields:
        values = fields[query_field]
    else:
        values = [
            item.get("name", ""),
            item.get("image", ""),
            item.get("server_ip", ""),
            item.get("id", ""),
            item.get("docker_id", ""),
            *item.get("ports", []),
        ]
    return any(keyword in str(value).lower() for value in values)


def _matches_filter(value: str, expected: str) -> bool:
    return not expected or str(value or "").lower() == expected.lower()


def paginate_items(items: list[dict[str, Any]], filters: DockerListFilters) -> dict[str, Any]:
    """应用筛选、排序与分页。"""
    filtered = [
        item
        for item in items
        if _matches_keyword(item, filters.keyword, filters.query_field)
        and _matches_filter(item.get("status", ""), filters.status)
        and _matches_filter(item.get("channel", ""), filters.channel)
        and _matches_filter(item.get("container_type", ""), filters.container_type)
        and (not filters.server or filters.server in {item.get("server_name"), item.get("server_ip")})
        and (not filters.image or filters.image.lower() in str(item.get("image", "")).lower())
    ]
    reverse = filters.sort.startswith("-")
    sort_key = filters.sort[1:] if reverse else filters.sort
    filtered.sort(key=lambda item: str(item.get(sort_key, "") or ""), reverse=reverse)

    page_size = min(max(int(filters.page_size or 20), 1), 100)
    page = max(int(filters.page or 1), 1)
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": filtered[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


class DockerService:
    """单机 Docker Engine 服务封装。

    多节点 Agent 后续可在这里抽象 server 参数，目前 MVP 只支持 local。
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import docker  # type: ignore
            except ImportError as exc:
                raise RuntimeError("Docker SDK 未安装，请安装 docker 依赖") from exc
            self._client = docker.from_env()
        return self._client

    def list_containers(self, filters: DockerListFilters) -> dict[str, Any]:
        containers = self.client.containers.list(all=True)
        items = [parse_container_summary(c) for c in containers]
        return paginate_items(items, filters)

    def list_images(self, server: str = "local") -> list[dict[str, Any]]:  # noqa: ARG002
        return [parse_image_summary(image) for image in self.client.images.list()]

    def container_logs(self, container_id: str, tail: int = 200) -> str:
        container = self.client.containers.get(container_id)
        raw = container.logs(tail=max(1, min(int(tail or 200), 2000)), timestamps=True)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw or "")

    def container_summary(self, container_id: str) -> dict[str, Any]:
        container = self.client.containers.get(container_id)
        return parse_container_summary(container)

    def open_terminal_socket(self, container_id: str) -> Any:
        command = ["sh", "-lc", "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi"]
        exec_info = self.client.api.exec_create(
            container_id,
            command,
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
        )
        exec_id = exec_info["Id"] if isinstance(exec_info, dict) else exec_info
        return self.client.api.exec_start(exec_id, tty=True, socket=True)

    def create_container(self, payload: ContainerCreateRequest) -> dict[str, Any]:
        env = {item.key: item.value for item in payload.env}
        ports = {
            f"{item.container_port}/{item.protocol}": (item.host_ip, item.host_port)
            for item in payload.ports
        } or None
        volumes = {
            item.host_path: {"bind": item.container_path, "mode": item.mode}
            for item in payload.volumes
        } or None
        restart_policy = (
            {}
            if payload.restart_policy == "no"
            else {"Name": payload.restart_policy}
        )
        kwargs: dict[str, Any] = {
            "image": payload.image,
            "name": payload.name,
            "command": payload.command,
            "detach": True,
            "environment": env or None,
            "ports": ports,
            "volumes": volumes,
            "network": payload.network,
            "restart_policy": restart_policy,
            "labels": payload.labels or None,
        }
        if payload.cpu_limit:
            kwargs["nano_cpus"] = int(payload.cpu_limit * 1_000_000_000)
        if payload.memory_limit:
            kwargs["mem_limit"] = payload.memory_limit
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        container = self.client.containers.create(**kwargs)
        if payload.is_start_after_create:
            container.start()
            container.reload()
        return parse_container_summary(container)

    def start_container(self, container_id: str) -> dict[str, Any]:
        container = self.client.containers.get(container_id)
        container.start()
        container.reload()
        return parse_container_summary(container)

    def stop_container(self, container_id: str) -> dict[str, Any]:
        container = self.client.containers.get(container_id)
        container.stop(timeout=10)
        container.reload()
        return parse_container_summary(container)

    def restart_container(self, container_id: str) -> dict[str, Any]:
        container = self.client.containers.get(container_id)
        container.restart(timeout=10)
        container.reload()
        return parse_container_summary(container)

    def delete_container(self, container_id: str, force: bool = False) -> dict[str, Any]:
        container = self.client.containers.get(container_id)
        name = container.name
        short_id = _short_id(container.id)
        container.remove(force=force)
        return {"id": short_id, "name": name, "status": "removed"}
