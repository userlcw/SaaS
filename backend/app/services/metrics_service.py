"""服务器资源指标采样与短期缓存。"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class _CpuSample:
    idle: int
    total: int


class MetricsService:
    """采集 Linux 主机资源快照，并用 TTL 降低轮询开销。"""

    def __init__(self, cache_ttl_seconds: int = 30) -> None:
        self.cache_ttl_seconds = max(5, int(cache_ttl_seconds or 30))
        self._cache: dict[str, Any] | None = None
        self._cache_at = 0.0
        self._last_cpu_sample: _CpuSample | None = None
        self._last_network_sample: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        if self._cache and now - self._cache_at < self.cache_ttl_seconds:
            return self._cache

        data = {
            "cpu": self._cpu_snapshot(),
            "memory": self._memory_snapshot(),
            "disk": self._disk_snapshot(),
            "network": self._network_snapshot(),
            "sampled_at": datetime.now(UTC).isoformat(),
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }
        self._cache = data
        self._cache_at = now
        return data

    def _cpu_snapshot(self) -> dict[str, Any]:
        sample = self._read_cpu_sample()
        percent = 0.0
        if sample and self._last_cpu_sample:
            idle_delta = sample.idle - self._last_cpu_sample.idle
            total_delta = sample.total - self._last_cpu_sample.total
            if total_delta > 0:
                percent = max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100))
        elif hasattr(os, "getloadavg"):
            try:
                load1, _, _ = os.getloadavg()
                cpus = os.cpu_count() or 1
                percent = max(0.0, min(100.0, load1 / cpus * 100))
            except OSError:
                percent = 0.0
        if sample:
            self._last_cpu_sample = sample
        return {
            "percent": round(percent, 2),
            "cores": os.cpu_count() or 1,
        }

    def _read_cpu_sample(self) -> _CpuSample | None:
        try:
            with open("/proc/stat", "r", encoding="utf-8") as fh:
                fields = fh.readline().split()[1:]
        except OSError:
            return None
        values = [int(value) for value in fields[:8]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return _CpuSample(idle=idle, total=total)

    def _memory_snapshot(self) -> dict[str, Any]:
        values: dict[str, int] = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    key, raw = line.split(":", 1)
                    parts = raw.strip().split()
                    if parts:
                        values[key] = int(parts[0]) * 1024
        except OSError:
            values = {}

        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        used = max(0, total - available) if total else 0
        percent = used / total * 100 if total else 0
        return {
            "total": total,
            "used": used,
            "available": available,
            "percent": round(percent, 2),
        }

    def _disk_snapshot(self) -> dict[str, Any]:
        usage = shutil.disk_usage("/")
        percent = usage.used / usage.total * 100 if usage.total else 0
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(percent, 2),
        }

    def _network_snapshot(self) -> dict[str, Any]:
        total_rx = 0
        total_tx = 0
        try:
            with open("/proc/net/dev", "r", encoding="utf-8") as fh:
                lines = fh.readlines()[2:]
            for line in lines:
                name, raw = line.split(":", 1)
                if name.strip() == "lo":
                    continue
                parts = raw.split()
                total_rx += int(parts[0])
                total_tx += int(parts[8])
        except OSError:
            total_rx = total_tx = 0

        now = time.time()
        rx_rate = 0.0
        tx_rate = 0.0
        if self._last_network_sample:
            elapsed = max(1.0, now - float(self._last_network_sample["time"]))
            rx_rate = max(0.0, (total_rx - int(self._last_network_sample["rx"])) / elapsed)
            tx_rate = max(0.0, (total_tx - int(self._last_network_sample["tx"])) / elapsed)
        self._last_network_sample = {"time": now, "rx": total_rx, "tx": total_tx}
        return {
            "rx_bytes": total_rx,
            "tx_bytes": total_tx,
            "rx_rate": round(rx_rate, 2),
            "tx_rate": round(tx_rate, 2),
        }


metrics_service = MetricsService()
