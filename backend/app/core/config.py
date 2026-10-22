"""运行期配置。

设计要点：
1. 静态默认值来自环境变量 / .env（前缀 ``CG_``），由 pydantic-settings 解析。
2. 运行期覆盖值以 key-value 形式存放在数据库表 ``app_configs`` 中，
   读取时 **数据库值优先于默认值**，因此网页「设置」页修改后立即生效。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "cyber_gf.db"


class Settings(BaseSettings):
    """应用静态配置（可被 .env / 环境变量覆盖）。"""

    model_config = SettingsConfigDict(
        env_prefix="CG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 数据库：默认落在 backend/data/cyber_gf.db（启动时自动建目录）
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

    # LLM 提供方：mock | openai | ollama
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.8

    # 记忆与上下文
    memory_top_k: int = 5
    recent_window: int = 12
    reflect_every: int = 6

    # 世界书 / Lorebook 注入
    lore_enabled: bool = True
    lore_budget: int = 1200  # 单轮世界书注入预算（字符数近似 token）
    lore_scan_window: int = 12  # 关键词匹配所扫描的最近消息条数

    # 导入脱敏
    desensitize_enabled: bool = True
    desensitize_blacklist: str = ""  # 关键词黑名单：逗号 / 换行分隔，或 JSON 数组


settings = Settings()

# 可以在运行期被数据库覆盖的配置项
CONFIG_KEYS = [
    "llm_provider",
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_temperature",
    "memory_top_k",
    "recent_window",
    "reflect_every",
    "lore_enabled",
    "lore_budget",
    "lore_scan_window",
    "desensitize_enabled",
    "desensitize_blacklist",
]

# 返回前端时需要打码的敏感项
SECRET_KEYS = {"llm_api_key"}

DEFAULTS: Dict[str, Any] = {key: getattr(settings, key) for key in CONFIG_KEYS}


def _coerce(key: str, value: Any, default: Any) -> Any:
    """把数据库里的字符串值还原成与默认值同类型的 Python 值。"""
    if value is None:
        return default
    try:
        if isinstance(default, bool):
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(default, float):
            return float(value)
        if isinstance(default, int):
            return int(float(str(value).strip()))
        return str(value)
    except (TypeError, ValueError):
        return default


def get_runtime_config(db) -> Dict[str, Any]:
    """读取最终生效配置：DB 覆盖值 > .env / 环境变量 > 代码默认值。"""
    from app.models.models import AppConfig  # 局部导入，避免循环依赖

    cfg: Dict[str, Any] = dict(DEFAULTS)
    try:
        rows = db.query(AppConfig).all()
    except Exception:
        return cfg
    for row in rows:
        if row.key in CONFIG_KEYS and row.value is not None:
            cfg[row.key] = _coerce(row.key, row.value, DEFAULTS[row.key])
    return cfg


def set_runtime_config(db, values: Dict[str, Any]) -> Dict[str, Any]:
    """写入运行期覆盖值（只接受 CONFIG_KEYS 白名单内的键）。"""
    from app.models.models import AppConfig  # 局部导入，避免循环依赖

    for key, value in (values or {}).items():
        if key not in CONFIG_KEYS or value is None:
            continue
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        if row is None:
            db.add(AppConfig(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    return get_runtime_config(db)


def mask_secret(value: str) -> str:
    """API Key 打码：保留前 4 位与后 4 位。"""
    value = value or ""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def get_settings() -> Settings:
    """获取静态配置单例。"""
    return settings


def reset_settings() -> Settings:
    """重新从环境变量 / .env 加载静态配置。"""
    global settings, DEFAULTS
    settings = Settings()
    DEFAULTS = {key: getattr(settings, key) for key in CONFIG_KEYS}
    return settings


__all__ = [
    "BACKEND_DIR",
    "CONFIG_KEYS",
    "DATA_DIR",
    "DEFAULTS",
    "DEFAULT_DB_PATH",
    "SECRET_KEYS",
    "Settings",
    "get_runtime_config",
    "get_settings",
    "mask_secret",
    "reset_settings",
    "set_runtime_config",
    "settings",
]
