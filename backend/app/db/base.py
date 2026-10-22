"""数据库基础：引擎、会话工厂、Base、建表 + 轻量迁移。

刻意不使用 Alembic —— demo 阶段以 ``create_all`` 自动建表 + ``app.db.migrate``
里的 PRAGMA/ALTER TABLE 轻量迁移覆盖版本演进，零外部迁移成本。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("app.db.base")


class Base(DeclarativeBase):
    """所有模型的声明式基类。"""


def _prepare_sqlite_dir(url: str) -> None:
    """SQLite 文件所在目录不存在时自动创建。"""
    if not url.startswith("sqlite"):
        return
    rest = url[len("sqlite:///") :] if url.startswith("sqlite:///") else url
    if not rest or rest == ":memory:":
        return
    parent = Path(rest).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def _build_engine():
    url = settings.database_url
    _prepare_sqlite_dir(url)
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表 + 轻量迁移（幂等）。

    顺序很重要：先 ``create_all`` 建出**缺失的表**（如新增的 worldbook_entries），
    再由 ``run_migrations`` 给**已存在的老表补缺失列**（PRAGMA + ALTER TABLE），
    这样老库无需删库重建即可平滑升级。
    """
    from app.models import models  # noqa: F401  导入以注册所有表

    Base.metadata.create_all(bind=engine)

    try:
        from app.db.migrate import run_migrations

        run_migrations(engine)
    except Exception as exc:  # 迁移失败不阻断启动，但要在日志里说清楚
        logger.warning("轻量迁移执行失败（已跳过，不影响已有表）：%s", exc)


__all__ = ["Base", "SessionLocal", "engine", "get_db", "init_db"]
