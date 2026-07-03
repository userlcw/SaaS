"""FastAPI 应用入口。

启动（本地热加载）：
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api import api_router
from backend.app.core.logger import get_logger, setup_logging
from backend.app.core.middleware import AccessLogMiddleware
from backend.app.db.init_db import init_db
from backend.config import PROJECT_ROOT, settings

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("应用启动：env=%s prefix=%s", settings.app_env, settings.api_v1_prefix)
    init_db()
    try:
        yield
    finally:
        logger.info("应用关闭")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS（allow_credentials=True 要求 origin 不能为 "*"，否则浏览器不会带上 cookie）
_cors_origins = settings.cors_origin_list
_cors_allow_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 基础主机白名单（默认放开，部署时可通过反向代理或此处收紧）
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Gzip 压缩（>= 512B 才压缩，节省小响应开销）
app.add_middleware(GZipMiddleware, minimum_size=512)

# 统一访问日志（请求 ID、耗时、状态码、IP/UA 等）
app.add_middleware(AccessLogMiddleware)


# 静态资源固定长缓存 + 页面/接口不缓存
_STATIC_PREFIX = "/static/"
_STATIC_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-store, must-revalidate"


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """为响应附加安全头 + 缓存策略。"""
    response = await call_next(request)
    # 安全头
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        # 收紧：仅同源脚本/样式/图片；允许行内 SVG 与 data 图；禁止 iframe 嵌入
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

    # 缓存策略
    path = request.url.path
    if path.startswith(_STATIC_PREFIX):
        response.headers.setdefault("Cache-Control", _STATIC_CACHE)
    else:
        # HTML/接口/首页均不缓存，避免登录状态错乱
        response.headers.setdefault("Cache-Control", _NO_CACHE)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", "-")
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = {"code": detail["code"], "message": detail["message"], "data": None}
    else:
        body = {"code": exc.status_code, "message": str(detail), "data": None}
    if exc.status_code >= 500:
        logger.error("HTTP 异常 id=%s status=%s path=%s detail=%s", rid, exc.status_code, request.url.path, detail)
    else:
        logger.warning("HTTP 异常 id=%s status=%s path=%s detail=%s", rid, exc.status_code, request.url.path, detail)
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = getattr(request.state, "request_id", "-")
    logger.warning("参数校验失败 id=%s path=%s errors=%s", rid, request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={"code": 42200, "message": "请求参数不合法", "data": {"errors": exc.errors()}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "-")
    logger.exception("未处理异常 id=%s path=%s err=%s", rid, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "message": "服务器内部错误", "data": None},
    )


@app.get("/health", tags=["system"])
def health():
    return {"code": 0, "message": "ok", "data": {"status": "up"}}


app.include_router(api_router, prefix=settings.api_v1_prefix)

# ------------------------------------------------------------------
# 挂载前端静态资源（同源部署，避免跨源与硬编码地址）
# ------------------------------------------------------------------
_FRONTEND_DIR = PROJECT_ROOT / "frontend" / "public"
if _FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(_FRONTEND_DIR)),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def _index():
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    @app.get("/register", include_in_schema=False)
    def _register_page():
        return FileResponse(str(_FRONTEND_DIR / "register.html"))

    @app.get("/console", include_in_schema=False)
    def _console_page():
        return FileResponse(str(_FRONTEND_DIR / "containers.html"))

    @app.get("/console/containers", include_in_schema=False)
    def _console_containers_page():
        return FileResponse(str(_FRONTEND_DIR / "containers.html"))

    @app.get("/console/terminal", include_in_schema=False)
    def _console_terminal_page():
        return FileResponse(str(_FRONTEND_DIR / "terminal.html"))

    @app.get("/containers", include_in_schema=False)
    def _containers_page():
        return FileResponse(str(_FRONTEND_DIR / "containers.html"))
