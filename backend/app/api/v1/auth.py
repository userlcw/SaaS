"""认证相关 API：登录 / 当前用户 / 刷新 / 登出。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.app.core.logger import get_logger
from backend.app.core.mailer import MailerError, send_verification_code
from backend.app.core.rate_limit import client_ip_of, ip_limiter
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from backend.app.core.verification import email_code_store
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import (
    ApiResponse,
    LoginRequest,
    LoginResponseData,
    RegisterRequest,
    SendCodeRequest,
    TokenData,
    UserPublic,
)
from backend.app.services.auth_service import AuthError, authenticate, register
from backend.config import settings

router = APIRouter()
logger = get_logger(__name__)

_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,
)


# ---------------- 工具 ----------------
def _cookie_max_age_seconds() -> int:
    return int(settings.refresh_token_expire_days) * 24 * 3600


def _set_refresh_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=_cookie_max_age_seconds(),
        httponly=True,
        secure=bool(settings.cookie_secure),
        samesite=settings.cookie_samesite,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _clear_refresh_cookie(resp: Response) -> None:
    resp.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _too_many_requests(remain: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": 42902,
            "message": f"操作过于频繁，请在 {remain} 秒后重试",
        },
        headers={"Retry-After": str(remain)},
    )


# ---------------- 发送邮箱验证码 ----------------
@router.post(
    "/send-code",
    response_model=ApiResponse,
    summary="发送注册邮箱验证码",
    responses={
        200: {"description": "已发送"},
        409: {"description": "邮箱已被注册"},
        429: {"description": "请求过于频繁"},
        502: {"description": "邮件服务不可用"},
    },
)
def send_email_code(
    payload: SendCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """向指定邮箱发送 6 位数字验证码，用于注册流程。"""
    ip = client_ip_of(request)
    email = str(payload.email).strip().lower()
    logger.info("发送验证码请求：email=%s ip=%s", email, ip)

    # IP 限流
    allowed, remain = ip_limiter.check(ip)
    if not allowed:
        raise _too_many_requests(remain)

    if not settings.smtp_enabled:
        logger.error("SMTP 未配置，无法发送验证码")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": 50201, "message": "邮件服务未配置，请联系管理员"},
        )

    # 邮箱已注册：也拒绝发送，避免枚举/骚扰
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40901, "message": "该邮箱已被注册"},
        )

    # 节流：同一邮箱冷却 & 每小时上限
    ok, wait, reason = email_code_store.check_send_allowed(email)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": 42903, "message": reason},
            headers={"Retry-After": str(max(1, wait))},
        )

    code, ttl = email_code_store.issue(email)
    ttl_minutes = max(1, ttl // 60)
    try:
        send_verification_code(email, code, ttl_minutes)
    except MailerError as e:
        ip_limiter.on_failure(ip)
        logger.error("发送验证码失败 email=%s err=%s", email, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": 50202, "message": str(e) or "邮件发送失败，请稍后再试"},
        ) from e

    return ApiResponse(
        code=0,
        message=f"验证码已发送至 {email}，有效期 {ttl_minutes} 分钟",
        data={
            "email": email,
            "ttl_seconds": ttl,
            "resend_after_seconds": settings.email_code_resend_seconds,
        },
    )


# ---------------- 注册 ----------------
@router.post(
    "/register",
    response_model=ApiResponse,
    summary="邮箱注册",
    responses={
        200: {"description": "注册成功"},
        409: {"description": "邮箱已被注册"},
        422: {"description": "参数不合法"},
        429: {"description": "IP 请求过于频繁"},
    },
)
def register_user(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """使用邮箱 + 密码注册新账号。用户名由邮箱本地部分生成，可在后续设置中修改。"""
    ip = client_ip_of(request)
    logger.info("注册请求：email=%s ip=%s", payload.email, ip)

    # 复用 IP 限流：避免同一 IP 大量注册
    allowed, remain = ip_limiter.check(ip)
    if not allowed:
        logger.warning("注册被拒绝：IP 限流生效 ip=%s remain=%ss", ip, remain)
        raise _too_many_requests(remain)

    # 校验邮箱验证码（消费一次）
    ok, reason = email_code_store.verify(str(payload.email), payload.code)
    if not ok:
        ip_limiter.on_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40011, "message": reason or "邮箱验证码不正确"},
        )

    try:
        user = register(db, email=str(payload.email), password=payload.password)
    except AuthError as e:
        ip_limiter.on_failure(ip)
        raise HTTPException(
            status_code=e.http_status,
            detail={"code": e.code, "message": e.message},
        ) from e

    return ApiResponse(
        code=0,
        message="注册成功",
        data=UserPublic.model_validate(user).model_dump(mode="json"),
    )


# ---------------- 登录 ----------------
@router.post(
    "/login",
    response_model=ApiResponse,
    summary="用户登录",
    responses={
        200: {"description": "登录成功"},
        401: {"description": "用户名或密码错误"},
        403: {"description": "账号已停用"},
        429: {"description": "登录失败次数过多，已锁定或 IP 限流"},
    },
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """使用用户名/邮箱 + 密码登录，返回 access_token 与设置 refresh_token cookie。"""
    ip = client_ip_of(request)
    logger.info("登录请求：identifier=%s ip=%s", payload.username, ip)

    # IP 级限流
    allowed, remain = ip_limiter.check(ip)
    if not allowed:
        logger.warning("登录被拒绝：IP 限流生效 ip=%s remain=%ss", ip, remain)
        raise _too_many_requests(remain)

    try:
        user = authenticate(db, payload.username, payload.password)
    except AuthError as e:
        # 失败计入 IP 限流
        ip_limiter.on_failure(ip)
        raise HTTPException(
            status_code=e.http_status,
            detail={"code": e.code, "message": e.message},
        ) from e

    # 成功：清空 IP 限流
    ip_limiter.on_success(ip)

    access_token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    refresh_token = create_refresh_token(subject=user.id)
    _set_refresh_cookie(response, refresh_token)

    data = LoginResponseData(
        token=TokenData(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        ),
        user=UserPublic.model_validate(user),
    )
    return ApiResponse(code=0, message="登录成功", data=data.model_dump(mode="json"))


# ---------------- 刷新 ----------------
@router.post(
    "/refresh",
    response_model=ApiResponse,
    summary="用 refresh_token cookie 换取新的 access_token",
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> ApiResponse:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40104, "message": "缺少刷新凭据"},
        )
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise JWTError("wrong token type")
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError, TypeError):
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40105, "message": "刷新凭据无效或已过期"},
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40103, "message": "用户不存在或已停用"},
        )

    access_token = create_access_token(
        subject=user.id, extra_claims={"username": user.username}
    )
    # 旋转 refresh_token
    new_refresh = create_refresh_token(subject=user.id)
    _set_refresh_cookie(response, new_refresh)

    data = LoginResponseData(
        token=TokenData(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        ),
        user=UserPublic.model_validate(user),
    )
    return ApiResponse(code=0, message="ok", data=data.model_dump(mode="json"))


# ---------------- 当前用户 ----------------
def _get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "message": "缺少认证凭据"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("wrong token type")
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "message": "凭据无效或已过期"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40103, "message": "用户不存在或已停用"},
        )
    return user


@router.get("/me", response_model=ApiResponse, summary="获取当前登录用户")
def me(current_user: User = Depends(_get_current_user)) -> ApiResponse:
    return ApiResponse(
        code=0,
        message="ok",
        data=UserPublic.model_validate(current_user).model_dump(mode="json"),
    )


# ---------------- 登出 ----------------
@router.post("/logout", response_model=ApiResponse, summary="登出（清除 refresh_token cookie）")
def logout(response: Response, current_user: User = Depends(_get_current_user)) -> ApiResponse:
    _clear_refresh_cookie(response)
    logger.info("用户登出 user_id=%s", current_user.id)
    return ApiResponse(code=0, message="已登出", data=None)
