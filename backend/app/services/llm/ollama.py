"""Ollama 本地模型 Provider。

调用 ``POST {base_url}/api/chat``，``stream=true``，
每行一个 JSON，取 ``message.content``。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.services.llm.base import LLMError, LLMProvider, normalize_messages


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = "", api_key: str = "", model: str = "", **kw: Any) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, **kw)
        self.base_url = (self.base_url or "http://localhost:11434").rstrip("/")
        self.model = self.model or "qwen2.5:7b"

    @property
    def available(self) -> bool:
        return bool(self.model)

    def _payload(self, messages: Any) -> dict:
        return {
            "model": self.model,
            "messages": normalize_messages(messages),
            "stream": True,
            "options": {"temperature": self.temperature},
        }

    async def stream(self, messages: Any, **kw: Any) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        payload = self._payload(messages)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "ignore")[:400]
                        raise LLMError(f"Ollama 返回 {resp.status_code}: {detail}")
                    async for raw_line in resp.aiter_lines():
                        line = (raw_line or "").strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        piece = (obj.get("message") or {}).get("content")
                        if piece:
                            yield str(piece)
                        if obj.get("done"):
                            break
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接 {url}: {exc}") from exc


__all__ = ["OllamaProvider"]
