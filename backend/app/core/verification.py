"""邮箱验证码：内存存储 + 节流。

- 每个邮箱最多同时保留一份最新验证码
- resend_seconds 内不允许重复发送同一邮箱
- 每小时最多发送 max_per_hour 次
- 校验失败达到上限即视为无效，需要重新获取
- 单机进程内存实现；多实例部署请替换为 Redis
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List

from backend.config import settings


@dataclass
class _CodeEntry:
    code: str
    created_at: float
    expires_at: float
    attempts: int = 0  # 校验失败次数


@dataclass
class _RateEntry:
    # 最近一次发送时间与最近一小时的发送时间戳队列
    sends: List[float] = field(default_factory=list)


class EmailCodeStore:
    """邮箱验证码存储与限流。"""

    _MAX_ATTEMPTS = 5

    def __init__(self) -> None:
        self._codes: Dict[str, _CodeEntry] = {}
        self._rates: Dict[str, _RateEntry] = {}
        self._lock = threading.RLock()

    # ---------------- 内部工具 ----------------
    def _norm(self, email: str) -> str:
        return (email or "").strip().lower()

    def _trim_rate(self, entry: _RateEntry, now: float) -> None:
        cutoff = now - 3600
        entry.sends = [t for t in entry.sends if t >= cutoff]

    # ---------------- 发送前检查 ----------------
    def check_send_allowed(self, email: str) -> tuple[bool, int, str]:
        """(是否允许, 需要等待的秒数, 拒绝原因)。允许时秒数为 0，原因为空。"""
        email = self._norm(email)
        if not email:
            return False, 0, "邮箱地址无效"
        now = time.time()
        with self._lock:
            rate = self._rates.get(email)
            if rate:
                self._trim_rate(rate, now)
                if rate.sends:
                    last = rate.sends[-1]
                    delta = now - last
                    if delta < settings.email_code_resend_seconds:
                        remain = int(settings.email_code_resend_seconds - delta) + 1
                        return False, remain, f"请求过于频繁，请在 {remain} 秒后重试"
                if len(rate.sends) >= settings.email_code_max_per_hour:
                    return False, 3600, "该邮箱一小时内发送次数已达上限，请稍后再试"
        return True, 0, ""

    # ---------------- 记录发送 ----------------
    def issue(self, email: str) -> tuple[str, int]:
        """生成并保存新的验证码；返回 (code, ttl_seconds)。"""
        email = self._norm(email)
        now = time.time()
        code = self._generate_code(int(settings.email_code_length))
        ttl = int(settings.email_code_ttl_seconds)
        entry = _CodeEntry(code=code, created_at=now, expires_at=now + ttl)
        with self._lock:
            self._codes[email] = entry
            rate = self._rates.setdefault(email, _RateEntry())
            self._trim_rate(rate, now)
            rate.sends.append(now)
        return code, ttl

    # ---------------- 校验 ----------------
    def verify(self, email: str, code: str) -> tuple[bool, str]:
        """(是否通过, 失败原因)。通过时消费掉该验证码。"""
        email = self._norm(email)
        code = (code or "").strip()
        if not email or not code:
            return False, "验证码无效"
        now = time.time()
        with self._lock:
            entry = self._codes.get(email)
            if entry is None:
                return False, "请先获取邮箱验证码"
            if entry.expires_at < now:
                self._codes.pop(email, None)
                return False, "验证码已过期，请重新获取"
            entry.attempts += 1
            if entry.attempts > self._MAX_ATTEMPTS:
                self._codes.pop(email, None)
                return False, "验证码错误次数过多，请重新获取"
            if not secrets.compare_digest(entry.code, code):
                return False, "验证码不正确"
            # 成功：消费掉，避免重放
            self._codes.pop(email, None)
        return True, ""

    # ---------------- 生成 ----------------
    @staticmethod
    def _generate_code(length: int) -> str:
        length = max(4, min(10, int(length or 6)))
        # 全数字验证码，末位不为 0 的概率交给随机
        digits = "0123456789"
        return "".join(secrets.choice(digits) for _ in range(length))


email_code_store = EmailCodeStore()


__all__ = ["email_code_store", "EmailCodeStore"]
