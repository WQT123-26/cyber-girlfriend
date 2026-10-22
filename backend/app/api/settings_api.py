"""运行期配置 API（设置页）。

配置项以 key-value 存入 ``app_configs`` 表，读取时 **DB 值优先于默认值**。
``llm_api_key`` 返回时一律打码，避免密钥泄露到前端。
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_runtime_config, mask_secret, set_runtime_config
from app.db.base import get_db
from app.schemas.schemas import SettingsOut, SettingsUpdate
from app.services.importer.desensitize import APPLY_ORDER, CATEGORY_LABELS, PLACEHOLDERS
from app.services.llm.factory import is_demo_mode

router = APIRouter(prefix="/settings", tags=["settings"])

# 前端展示用的脱敏规则清单（顺序即应用顺序）
DESENSITIZE_RULE_LABELS = [
    {
        "key": key,
        "label": CATEGORY_LABELS.get(key, key),
        "placeholder": PLACEHOLDERS.get(key, ""),
    }
    for key in APPLY_ORDER
]

EDITABLE_KEYS = (
    "llm_provider",
    "llm_base_url",
    "llm_model",
    "memory_top_k",
    "recent_window",
    "reflect_every",
    "lore_enabled",
    "lore_budget",
    "lore_scan_window",
    "desensitize_enabled",
    "desensitize_blacklist",
)

# 数值型配置的取值范围（防止前端传入畸形值把上下文撑爆）
INT_RANGES = {
    "memory_top_k": (1, 50),
    "recent_window": (1, 100),
    "reflect_every": (1, 100),
    "lore_budget": (0, 20000),
    "lore_scan_window": (1, 100),
}


def _as_bool(value: Any, default: bool = False) -> bool:
    """宽松布尔解析：兼容 true/false、1/0、on/off、yes/no 字符串。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "是", "开"}


def build_settings_out(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "llm_provider": cfg.get("llm_provider"),
        "llm_base_url": cfg.get("llm_base_url"),
        "llm_model": cfg.get("llm_model"),
        "llm_temperature": cfg.get("llm_temperature"),
        "llm_api_key_masked": mask_secret(cfg.get("llm_api_key")),
        "llm_api_key_set": bool(str(cfg.get("llm_api_key") or "").strip()),
        "memory_top_k": cfg.get("memory_top_k"),
        "recent_window": cfg.get("recent_window"),
        "reflect_every": cfg.get("reflect_every"),
        "database_url": cfg.get("database_url"),
        "demo_mode": is_demo_mode(cfg),
        "provider_options": ["mock", "openai", "ollama"],
        # 世界书注入
        "lore_enabled": bool(cfg.get("lore_enabled", True)),
        "lore_budget": cfg.get("lore_budget"),
        "lore_scan_window": cfg.get("lore_scan_window"),
        # 导入脱敏
        "desensitize_enabled": bool(cfg.get("desensitize_enabled", True)),
        "desensitize_blacklist": cfg.get("desensitize_blacklist") or "",
        "desensitize_rules": list(DESENSITIZE_RULE_LABELS),
    }


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return build_settings_out(get_runtime_config(db))


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}

    for key in EDITABLE_KEYS:
        value = getattr(payload, key, None)
        if value is not None:
            updates[key] = value

    # api_key：为空表示不修改；回显的掩码值（含 *）视为未修改
    api_key = payload.llm_api_key
    if api_key is not None and "*" not in api_key:
        updates["llm_api_key"] = api_key.strip()

    if payload.llm_temperature is not None:
        updates["llm_temperature"] = max(0.0, min(2.0, float(payload.llm_temperature)))

    for key in ("memory_top_k", "recent_window", "reflect_every"):
        if key in updates:
            try:
                updates[key] = max(1, int(updates[key]))
            except (TypeError, ValueError):
                updates.pop(key)

    # 世界书 / 脱敏：数值做范围钳制，布尔做宽松解析（前端可能传 "true"/"0"）
    for key, (low, high) in INT_RANGES.items():
        if key in updates:
            try:
                updates[key] = max(low, min(high, int(float(updates[key]))))
            except (TypeError, ValueError):
                updates.pop(key)

    for key in ("lore_enabled", "desensitize_enabled"):
        if key in updates:
            updates[key] = _as_bool(updates[key], True)

    if "desensitize_blacklist" in updates:
        from app.services.importer.desensitize import parse_blacklist

        # 统一成逗号分隔文本存库，读取时再解析，避免前端格式差异
        updates["desensitize_blacklist"] = ",".join(parse_blacklist(updates["desensitize_blacklist"]))

    if "llm_provider" in updates and updates["llm_provider"] not in ("mock", "openai", "ollama"):
        updates["llm_provider"] = "mock"

    set_runtime_config(db, updates)

    # provider 变了，清掉缓存，下次请求重建
    from app.services.llm.factory import reset_provider_cache

    reset_provider_cache()

    return build_settings_out(get_runtime_config(db))


__all__ = ["router", "build_settings_out"]
