"""OpenAI 兼容 Provider。

适用于：OpenAI / DeepSeek / 月之暗面 / 通义 / 硅基流动 / vLLM / one-api 等
所有暴露 ``POST {base_url}/chat/completions`` 且支持 SSE 流式的服务。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.services.llm.base import LLMError, LLMProvider, normalize_messages


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url: str = "", api_key: str = "", model: str = "", **kw: Any) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, **kw)
        self.base_url = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = self.model or "gpt-4o-mini"

    @property
    def available(self) -> bool:
        return bool(self.model)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: Any) -> dict:
        return {
            "model": self.model,
            "messages": normalize_messages(messages),
            "stream": True,
            "temperature": self.temperature,
        }

    async def stream(self, messages: Any, **kw: Any) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(messages)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "ignore")[:400]
                        raise LLMError(f"OpenAI 兼容接口返回 {resp.status_code}: {detail}")
                    async for raw_line in resp.aiter_lines():
                        line = (raw_line or "").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if not data or data == "[DONE]":
                            if data == "[DONE]":
                                break
                            continue
                        try:
                            obj = json.loads(data)
                        except (TypeError, ValueError):
                            continue
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            yield str(piece)
        except httpx.HTTPError as exc:  # 网络层错误
            raise LLMError(f"无法连接 {url}: {exc}") from exc


__all__ = ["OpenAICompatProvider"]
