"""LLM Provider 抽象基类。

统一约定：
    * 消息格式 ``[{"role": "system|user|assistant", "content": str}, ...]``
    * ``stream(messages, **kw)`` 返回 **异步生成器**，逐块产出文本片段
    * ``complete(messages, **kw)`` 返回完整字符串

所有实现都必须允许 ``**kw`` 携带额外上下文（如 persona_card / mood / affection /
user_text / memories），Provider 可自行决定是否使用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


class LLMError(RuntimeError):
    """调用 LLM 失败。"""


def normalize_messages(messages: Any) -> List[Dict[str, str]]:
    """把任意输入规整为标准消息列表。"""
    result: List[Dict[str, str]] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        result.append({"role": role, "content": str(item.get("content") or "")})
    return result


class LLMProvider(ABC):
    """Provider 基类。"""

    name: str = "base"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        temperature: float = 0.8,
        timeout: float = 90.0,
        **extra: Any,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.temperature = float(temperature or 0.8)
        self.timeout = float(timeout or 90.0)
        self.extra = extra

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """Provider 是否具备被调用的基本条件（如必须填 base_url）。"""
        return True

    @property
    def is_demo(self) -> bool:
        return False

    @abstractmethod
    def stream(self, messages: Any, **kw: Any) -> AsyncIterator[str]:
        """异步生成器：逐块产出文本。子类用 ``async def`` + ``yield`` 实现。"""
        raise NotImplementedError

    async def complete(self, messages: Any, **kw: Any) -> str:
        """默认实现：把流式结果拼成完整字符串。"""
        chunks: List[str] = []
        async for piece in self.stream(messages, **kw):
            chunks.append(piece)
        return "".join(chunks)

    # ------------------------------------------------------------------
    def _context(self, messages: Any, kw: Dict[str, Any]) -> Dict[str, Any]:
        """合并 kw 与最后一条 user 消息，供 mock 等本地实现使用。"""
        ctx: Dict[str, Any] = dict(kw or {})
        if not ctx.get("user_text"):
            for item in reversed(normalize_messages(messages)):
                if item["role"] == "user":
                    ctx["user_text"] = item["content"]
                    break
        ctx.setdefault("user_text", "")
        return ctx


__all__ = ["ChatMessage", "LLMError", "LLMProvider", "normalize_messages"]
