"""IP 级登录限流：滑动窗口 + 封禁期。

- 每个 IP 单独维护一个失败时间戳队列
- 当窗口内失败次数 >= max 时进入封禁期，直接拒绝所有登录请求
- 登录成功时清空该 IP 的失败计数
- 进程内内存实现，适合单机；多实例部署请替换为 Redis
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from backend.config import settings


class IPRateLimiter:
    def __init__(self, max_failures: int, window_seconds: int, block_seconds: int) -> None:
        self._max = max(1, int(max_failures))
        self._window = max(1, int(window_seconds))
        self._block = max(1, int(block_seconds))
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._blocked_until: Dict[str, float] = {}
        self._lock = threading.RLock()

    # ---------------- 内部工具 ----------------
    def _trim(self, ip: str, now: float) -> None:
        dq = self._events[ip]
        cutoff = now - self._window
        while dq and dq[0] < cutoff:
            dq.popleft()

    # ---------------- 对外接口 ----------------
    def check(self, ip: str) -> tuple[bool, int]:
        """返回 (是否允许, 剩余封禁秒数)。允许时剩余秒数为 0。"""
        if not ip:
            return True, 0
        now = time.time()
        with self._lock:
            until = self._blocked_until.get(ip)
            if until and until > now:
                return False, int(until - now) + 1
            elif until and until <= now:
                self._blocked_until.pop(ip, None)
                self._events.pop(ip, None)
        return True, 0

    def on_failure(self, ip: str) -> tuple[bool, int]:
        """记录一次失败；若触发封禁返回 (False, 剩余封禁秒数)。"""
        if not ip:
            return True, 0
        now = time.time()
        with self._lock:
            self._trim(ip, now)
            self._events[ip].append(now)
            if len(self._events[ip]) >= self._max:
                until = now + self._block
                self._blocked_until[ip] = until
                self._events[ip].clear()
                return False, int(self._block)
        return True, 0

    def on_success(self, ip: str) -> None:
        """登录成功：清空该 IP 的失败记录与封禁标记。"""
        if not ip:
            return
        with self._lock:
            self._events.pop(ip, None)
            self._blocked_until.pop(ip, None)


ip_limiter = IPRateLimiter(
    max_failures=settings.ip_rate_limit_max,
    window_seconds=settings.ip_rate_limit_window_seconds,
    block_seconds=settings.ip_rate_limit_block_seconds,
)


def client_ip_of(request) -> str:  # type: ignore[no-untyped-def]
    xff = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip") if hasattr(request, "headers") else None
    if real_ip:
        return real_ip.strip()
    return request.client.host if getattr(request, "client", None) else "-"
