from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.db.init_db import seed_initial_data
from backend.app.db.session import Base
from backend.app.models import docker as docker_models  # noqa: F401
from backend.app.models import rbac as rbac_models  # noqa: F401
from backend.app.models import user as user_models  # noqa: F401
from backend.app.models.user import User


def _memory_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, future=True)


def test_database_schema_contains_management_tables():
    engine, _ = _memory_db()
    inspector = inspect(engine)

    expected_tables = {
        "users",
        "server_nodes",
        "docker_containers",
        "docker_images",
        "container_labels",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "audit_logs",
    }
    assert expected_tables.issubset(set(inspector.get_table_names()))

    server_columns = {col["name"] for col in inspector.get_columns("server_nodes")}
    assert {"id", "name", "host", "endpoint", "status", "is_active", "created_at"}.issubset(server_columns)

    container_columns = {col["name"] for col in inspector.get_columns("docker_containers")}
    assert {
        "id",
        "server_node_id",
        "docker_id",
        "name",
        "image",
        "status",
        "container_type",
        "channel",
        "created_at",
        "updated_at",
    }.issubset(container_columns)

    audit_columns = {col["name"] for col in inspector.get_columns("audit_logs")}
    assert {
        "id",
        "user_id",
        "server_node_id",
        "container_id",
        "action",
        "result",
        "params_summary",
        "created_at",
    }.issubset(audit_columns)

    index_columns = {
        (index["name"], tuple(index["column_names"]))
        for index in inspector.get_indexes("docker_containers")
    }
    assert ("ix_docker_containers_status", ("status",)) in index_columns
    assert ("ix_docker_containers_channel", ("channel",)) in index_columns


def test_seed_initial_data_creates_permissions_admin_role_and_local_node():
    _, Session = _memory_db()
    with Session() as db:
        admin = User(
            username="admin_lcw",
            email="admin@example.com",
            password_hash="hash",
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()

        seed_initial_data(db, default_node_host="110.42.246.131")

        role_names = {role.name for role in db.query(rbac_models.Role).all()}
        permission_codes = {perm.code for perm in db.query(rbac_models.Permission).all()}
        node = db.query(docker_models.ServerNode).filter_by(name="local").one()
        user_role = db.query(rbac_models.UserRole).filter_by(user_id=admin.id).one()

    assert "admin" in role_names
    assert {"container:view", "container:create", "image:view", "audit:view"}.issubset(permission_codes)
    assert node.host == "110.42.246.131"
    assert user_role.role_id is not None


def test_seed_initial_data_updates_placeholder_local_node_host():
    _, Session = _memory_db()
    with Session() as db:
        db.add(
            docker_models.ServerNode(
                name="local",
                host="127.0.0.1",
                endpoint="unix:///var/run/docker.sock",
                status="online",
                is_active=True,
            )
        )
        db.commit()

        seed_initial_data(db, default_node_host="110.42.246.131")

        node = db.query(docker_models.ServerNode).filter_by(name="local").one()

    assert node.host == "110.42.246.131"
