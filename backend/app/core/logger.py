"""统一日志组件。

- 日志目录：<项目根>/logs/
- 日志文件命名：YYYYMMDD.log（不区分错误/正常，写入完整运行日志）
- 单文件超过 20MB 时：将当前文件压缩为 YYYYMMDD_序号.log.gz，然后新建同名 YYYYMMDD.log 继续写入
- 日期跨天时：自动切换到新日期的日志文件
"""
from __future__ import annotations

import gzip
import logging
import shutil
import sys
import threading
from datetime import datetime
from logging import Handler, LogRecord
from pathlib import Path

from backend.config import LOG_DIR

_MAX_BYTES = 20 * 1024 * 1024  # 20MB
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class DailySizeRotatingFileHandler(Handler):
    """按天切割 + 按大小压缩滚动的日志 Handler。"""

    def __init__(self, log_dir: Path, max_bytes: int = _MAX_BYTES, encoding: str = "utf-8") -> None:
        super().__init__()
        self._log_dir = log_dir
        self._max_bytes = max_bytes
        self._encoding = encoding
        self._lock = threading.RLock()
        self._current_date: str = ""
        self._stream = None
        self._current_path: Path | None = None
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._open_stream_for_today()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _today_str(self) -> str:
        return datetime.now().strftime("%Y%m%d")

    def _open_stream_for_today(self) -> None:
        self._current_date = self._today_str()
        self._current_path = self._log_dir / f"{self._current_date}.log"
        self._stream = open(self._current_path, "a", encoding=self._encoding)

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.flush()
                self._stream.close()
            finally:
                self._stream = None

    def _next_archive_index(self) -> int:
        assert self._current_path is not None
        index = 1
        while True:
            candidate = self._log_dir / f"{self._current_date}_{index}.log.gz"
            if not candidate.exists():
                return index
            index += 1

    def _compress_current(self) -> None:
        """将当前日志压缩为 gz，压缩后清空原文件以继续写入。"""
        if self._current_path is None or not self._current_path.exists():
            return
        index = self._next_archive_index()
        archive = self._log_dir / f"{self._current_date}_{index}.log.gz"
        self._close_stream()
        with open(self._current_path, "rb") as fin, gzip.open(archive, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        # 清空原文件后继续写入同名 YYYYMMDD.log
        self._current_path.unlink(missing_ok=True)
        self._stream = open(self._current_path, "a", encoding=self._encoding)

    def _should_rollover_date(self) -> bool:
        return self._today_str() != self._current_date

    def _should_rollover_size(self, msg_size: int) -> bool:
        if self._current_path is None or not self._current_path.exists():
            return False
        try:
            return (self._current_path.stat().st_size + msg_size) > self._max_bytes
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Handler API
    # ------------------------------------------------------------------
    def emit(self, record: LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            data = msg.encode(self._encoding, errors="replace")
            with self._lock:
                if self._should_rollover_date():
                    self._close_stream()
                    self._open_stream_for_today()
                if self._should_rollover_size(len(data)):
                    self._compress_current()
                if self._stream is None:
                    self._open_stream_for_today()
                assert self._stream is not None
                self._stream.write(msg)
                self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._lock:
            self._close_stream()
        super().close()


_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化根日志器（幂等）。"""
    global _configured
    root = logging.getLogger()
    if _configured:
        return root

    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = DailySizeRotatingFileHandler(LOG_DIR)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    # 移除默认 handler，避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # 让第三方库日志也进入文件（统一在一份日志中排查）
    _bind_third_party_loggers(level)

    _configured = True
    return root


def _bind_third_party_loggers(level: int) -> None:
    """让 uvicorn / fastapi / sqlalchemy / httpx 等日志统一写入项目日志。"""
    named_levels = {
        "uvicorn": level,
        "uvicorn.error": level,
        "uvicorn.access": level,
        "fastapi": level,
        "sqlalchemy.engine": logging.WARNING,  # 需要 SQL 详情时改为 INFO
        "sqlalchemy.pool": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "watchfiles": logging.WARNING,
    }
    for name, lvl in named_levels.items():
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        # 交给 root handler 处理，避免重复
        lg.propagate = True
        for h in list(lg.handlers):
            lg.removeHandler(h)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
