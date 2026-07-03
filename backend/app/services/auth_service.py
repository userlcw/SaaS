"""认证业务逻辑。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.logger import get_logger
from backend.app.core.security import dummy_verify_password, hash_password, verify_password
from backend.app.models.user import User
from backend.config import settings

logger = get_logger(__name__)


class AuthError(Exception):
    """认证异常基类。"""

    code: int = 40001
    message: str = "认证失败"
    http_status: int = 401

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class InvalidCredentialsError(AuthError):
    code = 40101
    message = "用户名或密码错误"
    http_status = 401


class UserInactiveError(AuthError):
    code = 40301
    message = "账号已被停用，请联系管理员"
    http_status = 403


class UserLockedError(AuthError):
    code = 42901
    message = "登录失败次数过多，账号已临时锁定"
    http_status = 429


class EmailAlreadyExistsError(AuthError):
    code = 40901
    message = "该邮箱已被注册"
    http_status = 409


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _get_user_by_identifier(db: Session, identifier: str) -> Optional[User]:
    """按用户名或邮箱查询（参数化查询，天然防 SQL 注入）。"""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    return (
        db.query(User)
        .filter(or_(User.username == identifier, User.email == identifier))
        .first()
    )


def authenticate(db: Session, identifier: str, password: str) -> User:
    """校验凭据；抛出 AuthError 子类表示不同失败原因。"""
    user = _get_user_by_identifier(db, identifier)

    # 统一返回“凭据错误”，避免暴露账号是否存在
    if user is None:
        # 消耗与真实校验相近的时间，抵御时序枚举
        dummy_verify_password(password)
        logger.warning("登录失败：用户不存在 identifier=%s", identifier)
        raise InvalidCredentialsError()

    # 锁定判断
    if user.locked_until is not None and user.locked_until > _now_utc():
        logger.warning("登录被拒绝：账号处于锁定期 user_id=%s until=%s", user.id, user.locked_until)
        raise UserLockedError()

    if not user.is_active:
        logger.warning("登录被拒绝：账号已停用 user_id=%s", user.id)
        raise UserInactiveError()

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.login_max_failures:
            user.locked_until = _now_utc() + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count = 0
            db.commit()
            logger.warning("登录失败次数超限，账号锁定 user_id=%s", user.id)
            raise UserLockedError()
        db.commit()
        logger.warning("登录失败：密码错误 user_id=%s attempts=%s", user.id, user.failed_login_count)
        raise InvalidCredentialsError()

    # 登录成功：重置计数
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now_utc()
    db.commit()
    db.refresh(user)
    logger.info("登录成功 user_id=%s username=%s", user.id, user.username)
    return user


def _derive_username_from_email(email: str) -> str:
    """根据邮箱本地部分生成初始用户名，仅保留 [A-Za-z0-9_.-]。"""
    local = (email or "").split("@", 1)[0]
    cleaned = "".join(ch for ch in local if ch.isalnum() or ch in "._-")
    return (cleaned or "user")[:64]


def register(db: Session, email: str, password: str) -> User:
    """基于邮箱创建新用户；邮箱已存在则抛出 EmailAlreadyExistsError。"""
    email = (email or "").strip().lower()
    if not email:
        raise AuthError("邮箱不能为空")

    exists = db.query(User).filter(User.email == email).first()
    if exists is not None:
        logger.warning("注册失败：邮箱已存在 email=%s", email)
        raise EmailAlreadyExistsError()

    # 生成不冲突的初始用户名（邮箱本地部分 → 附加数字后缀）
    base_username = _derive_username_from_email(email)
    username = base_username
    suffix = 1
    while db.query(User).filter(User.username == username).first() is not None:
        suffix += 1
        username = f"{base_username[:60]}{suffix}"

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("注册失败：唯一约束冲突 email=%s", email)
        raise EmailAlreadyExistsError()
    db.refresh(user)
    logger.info("注册成功 user_id=%s email=%s username=%s", user.id, user.email, user.username)
    return user
