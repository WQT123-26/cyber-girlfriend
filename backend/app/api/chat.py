"""聊天 API：SSE 流式输出。

事件类型：

* ``delta``  —— 文本块 ``{"type":"delta","text":"..."}``
* ``notice`` —— 状态提示（召回记忆 / 降级告警）
* ``meta``   —— ``{"mood":int,"affection":int}``
* ``error``  —— 出错信息
* ``done``   —— ``{"message_id":int,"mood":int,"affection":int,"memory_added":int}``
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.models import ChatSession
from app.schemas.schemas import ChatRequest
from app.services.chat.engine import ChatEngine, to_sse

router = APIRouter(prefix="/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/stream")
async def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    session = db.get(ChatSession, payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not (payload.content or "").strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    # 流式生成期间自行管理数据库会话，避免请求级 session 提前关闭
    engine = ChatEngine()

    async def event_source():
        try:
            async for event in engine.stream_reply(
                payload.session_id,
                payload.content,
                use_memory=payload.use_memory,
            ):
                yield to_sse(event)
        except asyncio.CancelledError:  # 客户端断开
            raise
        except Exception as exc:  # 兜底：任何异常都以 error 事件返回，前端可提示
            yield to_sse({"type": "error", "message": f"生成失败：{exc}"})

    return StreamingResponse(event_source(), media_type="text/event-stream", headers=SSE_HEADERS)


__all__ = ["router"]
