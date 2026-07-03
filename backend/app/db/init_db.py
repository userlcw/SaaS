"""数据库初始化：建表 + 内置管理员账号（仅当不存在时）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.core.logger import get_logger
from backend.app.core.security import hash_password
from backend.app.db.session import Base, SessionLocal, engine
from backend.app.models.docker import ServerNode
from backend.app.models.rbac import Permission, Role, RolePermission, UserRole
from backend.app.models.user import User

logger = get_logger(__name__)

# 默认管理员：仅在首次初始化时创建；生产环境请自行修改
_DEFAULT_ADMIN_USERNAME = "admin_lcw"
_DEFAULT_ADMIN_PASSWORD = "Xianyu12345@"
_DEFAULT_ADMIN_EMAIL = "admin@example.com"

_DEFAULT_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("container:view", "查看容器列表与详情"),
    ("container:create", "创建容器"),
    ("container:start", "启动容器"),
    ("container:stop", "停止容器"),
    ("container:restart", "重启容器"),
    ("container:delete", "删除容器"),
    ("container:logs", "查看容器日志"),
    ("container:exec", "进入容器终端"),
    ("image:view", "查看镜像列表"),
    ("server:view", "查看服务器节点"),
    ("server:manage", "管理服务器节点"),
    ("audit:view", "查看审计日志"),
    ("user:manage", "管理用户"),
    ("role:manage", "管理角色与权限"),
)


def create_all() -> None:
    """按模型创建所有表（幂等）。"""
    # 显式导入以确保元数据注册
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _ensure_default_admin(db: Session) -> None:
    exists = db.query(User).filter(User.username == _DEFAULT_ADMIN_USERNAME).first()
    if exists:
        return
    admin = User(
        username=_DEFAULT_ADMIN_USERNAME,
        email=_DEFAULT_ADMIN_EMAIL,
        password_hash=hash_password(_DEFAULT_ADMIN_PASSWORD),
        is_active=True,
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    logger.info("已创建默认管理员账号：%s（请尽快修改密码）", _DEFAULT_ADMIN_USERNAME)


def seed_initial_data(db: Session, default_node_host: str = "127.0.0.1") -> None:
    """写入默认权限、管理员角色和本机 Docker 节点（幂等）。"""
    permissions: dict[str, Permission] = {}
    for code, description in _DEFAULT_PERMISSIONS:
        permission = db.query(Permission).filter(Permission.code == code).first()
        if permission is None:
            permission = Permission(code=code, description=description)
            db.add(permission)
            db.flush()
        permissions[code] = permission

    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if admin_role is None:
        admin_role = Role(name="admin", description="系统管理员")
        db.add(admin_role)
        db.flush()

    existing_role_permission_ids = {
        row.permission_id
        for row in db.query(RolePermission).filter(RolePermission.role_id == admin_role.id).all()
    }
    for permission in permissions.values():
        if permission.id not in existing_role_permission_ids:
            db.add(RolePermission(role_id=admin_role.id, permission_id=permission.id))

    admin_user = db.query(User).filter(User.username == _DEFAULT_ADMIN_USERNAME).first()
    if admin_user is not None:
        exists = (
            db.query(UserRole)
            .filter(UserRole.user_id == admin_user.id, UserRole.role_id == admin_role.id)
            .first()
        )
        if exists is None:
            db.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

    local_node = db.query(ServerNode).filter(ServerNode.name == "local").first()
    if local_node is None:
        db.add(
            ServerNode(
                name="local",
                host=default_node_host,
                endpoint="unix:///var/run/docker.sock",
                status="online",
                is_active=True,
            )
        )
    elif local_node.host in ("", "127.0.0.1", "localhost") and default_node_host:
        local_node.host = default_node_host

    db.commit()


def init_db() -> None:
    create_all()
    with SessionLocal() as db:
        _ensure_default_admin(db)
        seed_initial_data(db)
