"""Docker 资产、标签与操作审计模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class ServerNode(Base):
    __tablename__ = "server_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    host: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), default="unix:///var/run/docker.sock", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="online", nullable=False, index=True)
    docker_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DockerContainer(Base):
    __tablename__ = "docker_containers"
    __table_args__ = (
        UniqueConstraint("server_node_id", "docker_id", name="uq_container_node_docker_id"),
        UniqueConstraint("server_node_id", "name", name="uq_container_node_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_node_id: Mapped[int] = mapped_column(
        ForeignKey("server_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    docker_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    short_id: Mapped[str] = mapped_column(String(24), default="", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    image: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    image_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    health: Mapped[str] = mapped_column(String(32), default="", nullable=False, index=True)
    container_type: Mapped[str] = mapped_column(String(64), default="other", nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(96), default="", nullable=False, index=True)
    ports_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    labels_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DockerImage(Base):
    __tablename__ = "docker_images"
    __table_args__ = (UniqueConstraint("server_node_id", "image_id", "repository", "tag", name="uq_image_node_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_node_id: Mapped[int] = mapped_column(
        ForeignKey("server_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    repository: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(128), default="latest", nullable=False, index=True)
    image_type: Mapped[str] = mapped_column(String(64), default="other", nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ContainerLabel(Base):
    __tablename__ = "container_labels"
    __table_args__ = (UniqueConstraint("container_id", "label_key", name="uq_container_label_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    container_id: Mapped[int] = mapped_column(
        ForeignKey("docker_containers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label_value: Mapped[str] = mapped_column(String(512), default="", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    server_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("server_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    container_id: Mapped[int | None] = mapped_column(
        ForeignKey("docker_containers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    params_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
