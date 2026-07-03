"""认证相关 Pydantic Schema。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=3, max_length=64, description="用户名或邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="登录密码")

    @field_validator("username")
    @classmethod
    def _strip_username(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("username 不能为空")
        return v


class RegisterRequest(BaseModel):
    """注册请求：邮箱 + 密码（含二次确认）+ 邮箱验证码。"""

    email: EmailStr = Field(..., max_length=128, description="电子邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="登录密码")
    confirm_password: str = Field(..., min_length=8, max_length=128, description="确认密码")
    code: str = Field(..., min_length=4, max_length=10, description="邮箱验证码")

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not re.search(r"[a-z]", v) or not re.search(r"[A-Z]", v) or not re.search(r"\d", v):
            raise ValueError("密码需同时包含大写字母、小写字母和数字")
        return v

    @field_validator("confirm_password")
    @classmethod
    def _password_match(cls, v: str, info) -> str:
        pwd = info.data.get("password")
        if pwd is not None and v != pwd:
            raise ValueError("两次输入的密码不一致")
        return v

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("验证码格式不正确")
        return v


class SendCodeRequest(BaseModel):
    """发送邮箱验证码请求。"""

    email: EmailStr = Field(..., max_length=128, description="电子邮箱")


class TokenData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="access_token 过期秒数")


class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginResponseData(BaseModel):
    token: TokenData
    user: UserPublic


class ApiResponse(BaseModel):
    """统一 API 响应体。"""

    code: int = 0
    message: str = "ok"
    data: Optional[dict] = None
