"""安全相关：密码哈希、JWT（access / refresh）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import settings

# bcrypt 密码哈希上下文
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 一个占位 bcrypt 哈希：用于用户不存在时的“假验签”，抵御时序枚举
# hash of a random string; 结构合法，verify 必然失败，但耗时接近真实校验
_DUMMY_BCRYPT_HASH = "$2b$12$3F1n3Y2y3m0oJqQzq5N9ke3S1S6ZBVe7z0uT8ZAKAWXaEO5tGxJYq"


def hash_password(plain_password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    if not plain_password:
        raise ValueError("password must not be empty")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文与哈希是否一致。"""
    if not plain_password or not hashed_password:
        return False
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def dummy_verify_password(plain_password: str) -> None:
    """用户不存在时执行的“假验证”，消耗与真实校验相近的时间，缓解时序枚举。"""
    try:
        _pwd_context.verify(plain_password or "", _DUMMY_BCRYPT_HASH)
    except Exception:
        pass


def _create_token(subject: str | int, token_type: str, expires_delta: timedelta,
                  extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(tz=timezone.utc)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": token_type,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str | int, extra_claims: dict[str, Any] | None = None) -> str:
    """生成短期 access token。"""
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims,
    )


def create_refresh_token(subject: str | int, extra_claims: dict[str, Any] | None = None) -> str:
    """生成长期 refresh token（存放于 httpOnly cookie）。"""
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        extra_claims,
    )


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT；失败抛 JWTError。"""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


# 兼容旧命名
decode_access_token = decode_token


__all__ = [
    "hash_password",
    "verify_password",
    "dummy_verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "decode_access_token",
    "JWTError",
]
