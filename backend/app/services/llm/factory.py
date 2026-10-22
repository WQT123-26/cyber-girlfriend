"""Provider 工厂：按运行期配置构建具体的 LLM Provider。

任何配置异常（缺 base_url / 未填 Key 等）都会**自动降级为 mock**，
保证 demo 在零配置环境下 100% 可用。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.core.config import get_runtime_config
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockProvider
from app.services.llm.ollama import OllamaProvider
from app.services.llm.openai_compat import OpenAICompatProvider

PROVIDER_NAMES = ["mock", "openai", "ollama"]


def build_provider(cfg: Dict[str, Any]) -> LLMProvider:
    """根据配置构建 Provider；不可用时回落到 mock。"""
    cfg = cfg or {}
    provider = str(cfg.get("llm_provider") or "mock").strip().lower()
    common = {
        "base_url": str(cfg.get("llm_base_url") or ""),
        "api_key": str(cfg.get("llm_api_key") or ""),
        "model": str(cfg.get("llm_model") or ""),
        "temperature": float(cfg.get("llm_temperature") or 0.8),
    }

    if provider == "openai":
        client = OpenAICompatProvider(**common)
        return client if client.available else MockProvider(fallback_reason="OpenAI 兼容接口未配置模型名")
    if provider == "ollama":
        client = OllamaProvider(**common)
        return client if client.available else MockProvider(fallback_reason="Ollama 未配置模型名")
    return MockProvider()


def get_provider(db) -> Tuple[LLMProvider, Dict[str, Any]]:
    """读取运行期配置并构建 Provider。"""
    cfg = get_runtime_config(db)
    return build_provider(cfg), cfg


def is_demo_mode(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """是否处于演示模式（mock）。

    ``cfg`` 省略时回落到静态配置（环境变量 / .env），便于启动阶段判断。
    """
    if cfg is None:
        from app.core.config import get_settings

        static = get_settings()
        cfg = {"llm_provider": static.llm_provider, "llm_model": static.llm_model}
    provider = str((cfg or {}).get("llm_provider") or "mock").strip().lower()
    if provider == "mock":
        return True
    return not bool((cfg or {}).get("llm_model"))


# Provider 缓存：仅用于设置变更后统一失效，避免出现「改了配置但仍旧对象」的观感问题。
_PROVIDER_CACHE: Dict[str, LLMProvider] = {}


def reset_provider_cache() -> None:
    """清空 Provider 缓存（设置页保存后调用）。"""
    _PROVIDER_CACHE.clear()


__all__ = [
    "PROVIDER_NAMES",
    "build_provider",
    "get_provider",
    "is_demo_mode",
    "reset_provider_cache",
]
