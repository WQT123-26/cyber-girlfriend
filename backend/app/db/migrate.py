"""SQLite 轻量迁移（无 Alembic）。

策略
----
启动时按「先建表、后补列」两步走：

1. ``Base.metadata.create_all`` —— 负责**缺失的表**（新增表零成本）。
2. ``run_migrations`` —— 用 ``PRAGMA table_info`` 逐表检查，发现**缺失的列**
   就 ``ALTER TABLE ... ADD COLUMN``，让旧库平滑升级，无需删库重建。

为什么要显式维护 DDL 字符串
---------------------------
SQLite 的 ``ALTER TABLE ADD COLUMN`` 对 NOT NULL 列强制要求默认值，
而 SQLAlchemy 的 ``default=`` 是 **Python 侧**默认值（不落 DDL），
直接照搬模型定义会报 ``Cannot add a NOT NULL column with default value NULL``。
因此这里维护一份 ``LEGACY_COLUMNS`` 白名单（类型 + DEFAULT 字面量），
再用模型元数据做兜底扫描（``_render_default`` 尽力还原默认值，
实在无法还原的 NOT NULL 列会跳过并记录到报告里，绝不静默改坏数据）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.base import Base

logger = logging.getLogger("app.db.migrate")

# 历史版本 → 当前版本新增的列（类型 + 默认值字面量）
LEGACY_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "personas": [
        ("creator_notes", "TEXT NOT NULL DEFAULT ''"),
        ("tags", "TEXT NOT NULL DEFAULT '[]'"),
        ("character_version", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ("card_spec", "VARCHAR(32) NOT NULL DEFAULT ''"),
        ("extensions", "TEXT NOT NULL DEFAULT '{}'"),
    ],
    "import_batches": [
        ("desensitize_enabled", "BOOLEAN NOT NULL DEFAULT 1"),
        ("desensitize_stats", "TEXT NOT NULL DEFAULT '{}'"),
    ],
}

# 本次迭代新增的整表（缺失时由 create_all 建；列变更不会发生）
NEW_TABLES = ("worldbook_entries",)


def _render_default(column: Any) -> Optional[str]:
    """尽力从模型列定义还原 SQL 默认值字面量；无法还原返回 ``None``。"""
    server_default = getattr(column, "server_default", None)
    if server_default is not None:
        try:
            return str(server_default.arg)
        except Exception:  # pragma: no cover - 极端情况
            return None

    default = getattr(column, "default", None)
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if callable(value):
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _column_type(column: Any) -> str:
    try:
        return str(column.type.compile(dialect=None))
    except Exception:
        return "TEXT"


def _existing_columns(conn: Any, table: str) -> List[str]:
    rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
    return [str(row[1]) for row in rows]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).fetchone()
    return bool(row)


def run_migrations(engine: Engine, verbose: bool = True) -> Dict[str, Any]:
    """执行轻量迁移，返回报告字典。"""
    report: Dict[str, Any] = {
        "dialect": engine.dialect.name,
        "executed": False,
        "added_columns": [],
        "added_tables": [],
        "skipped": [],
        "checked_tables": 0,
    }
    if engine.dialect.name != "sqlite":
        report["skipped"].append(f"非 SQLite 数据库（{engine.dialect.name}），跳过轻量迁移")
        return report

    inspected = {table.name for table in Base.metadata.sorted_tables}
    statements: List[str] = []

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            name = table.name
            report["checked_tables"] += 1
            if not _table_exists(conn, name):
                # 交给 create_all；此处只记录
                report["skipped"].append(f"表 {name} 不存在，交给 create_all 新建")
                continue

            existing = set(_existing_columns(conn, name))
            legacy = dict(LEGACY_COLUMNS.get(name, []))
            for column in table.columns:
                column_name = column.name
                if column_name in existing:
                    continue

                ddl = legacy.get(column_name)
                if ddl is None:
                    column_type = _column_type(column)
                    if column.nullable:
                        ddl = column_type
                    else:
                        rendered = _render_default(column)
                        if rendered is None:
                            report["skipped"].append(
                                f"表 {name} 缺列 {column_name}（NOT NULL 且无法还原默认值），已跳过，需人工处理"
                            )
                            continue
                        ddl = f"{column_type} NOT NULL DEFAULT {rendered}"
                statements.append(f'ALTER TABLE "{name}" ADD COLUMN "{column_name}" {ddl}')

        for statement in statements:
            conn.execute(text(statement))
            report["added_columns"].append(statement)
        report["executed"] = bool(statements)

        for name in NEW_TABLES:
            if name in inspected and not _table_exists(conn, name):
                report["added_tables"].append(name)

    if verbose:
        if report["added_columns"]:
            logger.info("轻量迁移完成，新增 %d 个列", len(report["added_columns"]))
        else:
            logger.info("轻量迁移检查完成，数据库结构已是最新")
        for item in report["skipped"]:
            logger.info("迁移提示：%s", item)
    return report


__all__ = ["LEGACY_COLUMNS", "NEW_TABLES", "run_migrations"]
