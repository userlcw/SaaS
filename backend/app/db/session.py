"""数据库连接与会话。"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings

# SQLite 需要额外参数以允许跨线程使用；其他数据库无此需求
_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


class Base(DeclarativeBase):
    """ORM 声明式基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求内数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
