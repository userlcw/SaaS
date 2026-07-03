"""HTTP 请求 / 响应访问日志中间件。

为每个请求：
- 生成唯一 request_id（也回写响应头 X-Request-ID）
- 记录 method、path、query、client_ip、UA、状态码、耗时(ms)、响应长度
- 异常情况打印完整堆栈，便于在 logs/YYYYMMDD.log 中定位问题
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.core.logger import get_logger

logger = get_logger("app.access")

# 静态资源等噪声路径以 DEBUG 级别打点
_QUIET_PREFIXES = ("/static", "/favicon")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "-"


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        method = request.method
        path = request.url.path
        query = request.url.query or "-"
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "-")

        is_quiet = any(path.startswith(p) for p in _QUIET_PREFIXES)
        log_start = logger.debug if is_quiet else logger.info

        log_start(
            "→ req id=%s ip=%s method=%s path=%s query=%s ua=%s",
            request_id, ip, method, path, query, ua,
        )

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            # 交给全局异常处理器返回响应，这里仅补充上下文日志
            logger.exception(
                "× req id=%s ip=%s method=%s path=%s 未处理异常",
                request_id, ip, method, path,
            )
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_end = logger.debug if is_quiet else logger.info
            log_end(
                "← resp id=%s status=%s method=%s path=%s cost=%.2fms",
                request_id, status_code, method, path, elapsed_ms,
            )
