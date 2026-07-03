"""Docker 管理接口 Schema。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PortMapping(BaseModel):
    host_ip: str = "0.0.0.0"
    host_port: int = Field(..., ge=1, le=65535)
    container_port: int = Field(..., ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"


class EnvVar(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(default="", max_length=4096)

    @field_validator("key")
    @classmethod
    def _strip_key(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("环境变量名称不能为空")
        return value


class VolumeMapping(BaseModel):
    host_path: str = Field(..., min_length=1, max_length=512)
    container_path: str = Field(..., min_length=1, max_length=512)
    mode: Literal["rw", "ro"] = "rw"


class ContainerCreateRequest(BaseModel):
    server: str = "local"
    image: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    command: str | None = Field(default=None, max_length=1024)
    env: list[EnvVar] = Field(default_factory=list)
    ports: list[PortMapping] = Field(default_factory=list)
    volumes: list[VolumeMapping] = Field(default_factory=list)
    network: str | None = Field(default=None, max_length=128)
    restart_policy: Literal["no", "always", "unless-stopped", "on-failure"] = "unless-stopped"
    cpu_limit: float | None = Field(default=None, ge=0.1)
    memory_limit: str | None = Field(default=None, max_length=32)
    labels: dict[str, str] = Field(default_factory=dict)
    is_start_after_create: bool = True

    @field_validator("labels")
    @classmethod
    def _validate_labels(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(k).strip(): str(v).strip() for k, v in (value or {}).items() if str(k).strip()}


class DockerActionResponse(BaseModel):
    id: str
    name: str
    status: str
    extra: dict[str, Any] = Field(default_factory=dict)
