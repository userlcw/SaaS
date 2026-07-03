"""仪表盘、用户与审计查询 API。"""
from __future__ import annotations

import json
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.api.v1.auth import _get_current_user
from backend.app.api.v1.containers import get_current_user_for_docker
from backend.app.db.session import get_db
from backend.app.models.docker import AuditLog
from backend.app.models.rbac import Permission, Role, RolePermission, UserRole
from backend.app.models.user import User
from backend.app.schemas.auth import ApiResponse
from backend.app.services.metrics_service import metrics_service

router = APIRouter()


def _is_admin(user: Any) -> bool:
    if isinstance(user, dict):
        return bool(user.get("is_admin"))
    return bool(getattr(user, "is_admin", False))


def get_current_user_for_admin(current_user: User = Depends(_get_current_user)) -> User:
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权限执行该操作"},
        )
    return current_user


@router.get("/dashboard/metrics", response_model=ApiResponse, summary="服务器资源指标")
def dashboard_metrics(current_user: User = Depends(get_current_user_for_docker)) -> ApiResponse:
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权限执行该操作"},
        )
    return ApiResponse(code=0, message="ok", data=metrics_service.snapshot())


def _page_payload(items: list[dict[str, Any]], total: int, page: int, page_size: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


def _roles_and_permissions(db: Session, user_id: int) -> tuple[list[str], list[str]]:
    role_rows = (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .order_by(Role.name.asc())
        .all()
    )
    roles = [role.name for role in role_rows]
    if not role_rows:
        return roles, []
    role_ids = [role.id for role in role_rows]
    permission_rows = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id.in_(role_ids))
        .order_by(Permission.code.asc())
        .all()
    )
    permissions = sorted({permission.code for permission in permission_rows})
    return roles, permissions


@router.get("/users", response_model=ApiResponse, summary="用户列表与权限")
def list_users(
    keyword: str = "",
    status_value: str = Query("", alias="status"),
    role: str = "",
    sort: str = "username",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_for_admin),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> ApiResponse:
    query = db.query(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(or_(User.username.like(like), User.email.like(like)))
    if status_value == "active":
        query = query.filter(User.is_active.is_(True))
    elif status_value == "disabled":
        query = query.filter(User.is_active.is_(False))
    if role:
        query = query.join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        query = query.filter(Role.name == role)

    sort_map = {
        "username": User.username.asc(),
        "-username": User.username.desc(),
        "created_at": User.created_at.asc(),
        "-created_at": User.created_at.desc(),
        "last_login_at": User.last_login_at.asc(),
        "-last_login_at": User.last_login_at.desc(),
    }
    query = query.order_by(sort_map.get(sort, User.username.asc()))
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for user in users:
        roles, permissions = _roles_and_permissions(db, user.id)
        items.append(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "roles": roles,
                "permissions": permissions,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else "",
                "created_at": user.created_at.isoformat() if user.created_at else "",
            }
        )
    return ApiResponse(code=0, message="ok", data=_page_payload(items, total, page, page_size))


def _parse_params_summary(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {"raw": raw}
    except json.JSONDecodeError:
        return {"raw": raw or ""}


@router.get("/audit-logs", response_model=ApiResponse, summary="审计日志")
def list_audit_logs(
    user: str = "",
    action: str = "",
    start_time: str = Query("", alias="startTime"),
    end_time: str = Query("", alias="endTime"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_for_admin),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> ApiResponse:
    query = db.query(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id)
    if user:
        query = query.filter(User.username.like(f"%{user.strip()}%"))
    if action:
        query = query.filter(AuditLog.action == action)
    if start_time:
        query = query.filter(AuditLog.created_at >= start_time)
    if end_time:
        query = query.filter(AuditLog.created_at <= end_time)

    query = query.order_by(AuditLog.created_at.desc())
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for log, username in rows:
        params = _parse_params_summary(log.params_summary)
        items.append(
            {
                "id": log.id,
                "username": username or "system",
                "action": log.action,
                "result": log.result,
                "ip": log.ip,
                "device": params.get("device", ""),
                "before": params.get("before"),
                "after": params.get("after"),
                "container": params.get("container_name") or params.get("container_id") or "",
                "params": params,
                "error_message": log.error_message,
                "duration_ms": log.duration_ms,
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
        )
    return ApiResponse(code=0, message="ok", data=_page_payload(items, total, page, page_size))
