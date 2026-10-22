"""聊天引擎。

上下文组装顺序（严格）：

    1. system —— 结构化人设提示词（build_system_prompt）
    2. system —— 【长期记忆】召回块
    3. system —— 【会话摘要】
    4. user / assistant —— 最近 recent_window 条历史消息
    5. user —— 用户当前输入

世界书（Lorebook）在 1~5 组装完成后按 ``position`` 二次注入：
    * ``before_char`` 插到 system prompt 之前
    * ``after_char``  插到 system prompt 之后
    * ``at_depth``    插到距末尾 ``depth`` 条消息之前

流式生成时**边产出边落库**：先落库 user 消息 → 流式产出 assistant 内容 →
结束后落库 assistant 消息 → 更新 mood / affection → 触发记忆反思。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from app.core.config import get_runtime_config
from app.db.base import SessionLocal
from app.models.models import ChatSession, Message, Persona
from app.services.llm.base import LLMError, LLMProvider
from app.services.llm.factory import build_provider
from app.services.llm.mock import MockProvider
from app.services.lore.matcher import collect_hits, inject_into_messages, injection_summary
from app.services.memory.reflect import maybe_reflect
from app.services.memory.store import retrieve
from app.services.persona.prompt import build_memory_block, build_system_prompt

POSITIVE_WORDS = [
    "谢谢", "喜欢", "爱你", "想你", "抱抱", "开心", "辛苦", "可爱",
    "乖", "好棒", "加油", "陪", "么么", "晚安", "别累着",
]
NEGATIVE_WORDS = [
    "滚", "烦", "讨厌", "闭嘴", "无聊", "分手", "不喜欢", "别烦我", "有病", "傻",
]


def _clamp(value: Any, default: int = 50) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, number))


def update_state(mood: int, affection: int, user_text: str, reply_text: str = "") -> Dict[str, int]:
    """规则式状态演进：关键词 + 长度 + 反馈，结果夹紧到 0~100。"""
    mood_value = _clamp(mood, 65)
    affection_value = _clamp(affection, 50)
    text = str(user_text or "")
    length = len(text)

    # 长度：愿意多说话本身就是正向信号
    if length >= 20:
        affection_value += 1
    if length >= 40:
        mood_value += 1
    # 关键词
    positive_hits = sum(1 for word in POSITIVE_WORDS if word in text)
    negative_hits = sum(1 for word in NEGATIVE_WORDS if word in text)
    mood_value += min(positive_hits, 3)
    affection_value += min(positive_hits, 3)
    mood_value -= min(negative_hits * 2, 6)
    affection_value -= min(negative_hits * 2, 6)
    # 互动本身的正向漂移
    mood_value += 1
    affection_value += 1
    # 提问 = 想聊下去
    if any(mark in text for mark in ("?", "？", "吗", "呢")):
        mood_value += 1
    # 回复很长说明投入
    if len(reply_text or "") >= 60:
        mood_value += 1

    return {"mood": _clamp(mood_value, 65), "affection": _clamp(affection_value, 50)}


def apply_feedback_to_state(mood: int, affection: int, action: str) -> Dict[str, int]:
    """反馈对状态的影响。"""
    mood_value = _clamp(mood, 65)
    affection_value = _clamp(affection, 50)
    if action == "like":
        mood_value += 4
        affection_value += 4
    elif action == "dislike":
        mood_value -= 4
        affection_value -= 3
    else:  # rewrite
        mood_value += 1
        affection_value += 2
    return {"mood": _clamp(mood_value, 65), "affection": _clamp(affection_value, 50)}


class ChatEngine:
    """一次流式回复的完整执行者。"""

    def __init__(self, db=None, provider: Optional[LLMProvider] = None, config: Optional[Dict[str, Any]] = None):
        self._external_db = db
        self._provider = provider
        self._config = config

    # ------------------------------------------------------------------
    async def stream_reply(
        self,
        session_id: int,
        user_text: str,
        use_memory: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        """产出事件流：delta / meta / notice / error / done。"""
        owns_db = self._external_db is None
        db = self._external_db or SessionLocal()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session is None:
                yield {"type": "error", "message": f"会话 {session_id} 不存在"}
                return
            persona = db.query(Persona).filter(Persona.id == session.persona_id).first()
            if persona is None:
                yield {"type": "error", "message": "该会话关联的人格已被删除"}
                return

            user_text = str(user_text or "").strip()
            if not user_text:
                yield {"type": "error", "message": "消息内容不能为空"}
                return

            cfg = self._config or get_runtime_config(db)
            provider = self._provider or build_provider(cfg)
            top_k = max(1, int(cfg.get("memory_top_k") or 5))
            recent_window = max(2, int(cfg.get("recent_window") or 12))
            reflect_every = max(1, int(cfg.get("reflect_every") or 6))

            # 1) 落库用户消息
            user_message = Message(session_id=session.id, role="user", content=user_text)
            db.add(user_message)
            db.commit()
            db.refresh(user_message)

            # 2) 召回长期记忆
            memories = retrieve(db, persona.id, user_text, top_k) if use_memory else []
            memory_texts = [m.content for m in memories]
            if memory_texts:
                yield {"type": "notice", "level": "memory", "message": f"召回 {len(memory_texts)} 条长期记忆",
                       "items": memory_texts}

            # 3) 组装上下文
            history_rows = (
                db.query(Message)
                .filter(Message.session_id == session.id, Message.id < user_message.id)
                .order_by(Message.id.desc())
                .limit(recent_window)
                .all()
            )
            history_rows.reverse()

            messages: List[Dict[str, str]] = [
                {
                    "role": "system",
                    "content": build_system_prompt(
                        persona,
                        user_nickname=persona.nickname_for_user,
                        mood=session.mood,
                        affection=session.affection,
                        memories=None,
                    ),
                }
            ]
            if memory_texts:
                messages.append({"role": "system", "content": build_memory_block(memories)})
            if (session.summary or "").strip():
                messages.append({"role": "system", "content": f"【会话摘要】{session.summary.strip()}"})
            for row in history_rows:
                if row.role in ("user", "assistant"):
                    messages.append({"role": row.role, "content": row.content})
            messages.append({"role": "user", "content": user_text})

            # 3.5) 世界书 / Lorebook 注入（按 position 二次插入）
            lore_hits: List[Any] = []
            lore_stats: Dict[str, Any] = {}
            if cfg.get("lore_enabled", True):
                try:
                    scan_rows = [
                        {"role": row.role, "content": row.content}
                        for row in history_rows
                        if row.role in ("user", "assistant")
                    ]
                    scan_rows.append({"role": "user", "content": user_text})
                    lore_hits, lore_stats = collect_hits(db, persona.id, messages=scan_rows)
                    if lore_hits:
                        messages = inject_into_messages(messages, lore_hits)
                        yield {
                            "type": "notice",
                            "level": "lore",
                            "message": f"注入 {len(lore_hits)} 条世界设定",
                            "items": [hit.content[:40] for hit in lore_hits],
                            "detail": injection_summary(lore_hits),
                        }
                except Exception as exc:  # 世界书失败不影响主流程
                    lore_hits = []
                    lore_stats = {}
                    yield {"type": "notice", "level": "warn", "message": f"世界书注入跳过：{exc}"}

            extra = {
                "persona_card": persona.card(),
                "persona_name": persona.name,
                "relation": persona.relation,
                "nickname_for_user": persona.nickname_for_user,
                "mood": session.mood,
                "affection": session.affection,
                "user_text": user_text,
                "memories": memory_texts,
            }

            # 4) 流式生成
            pieces: List[str] = []
            active_provider = provider
            try:
                async for chunk in active_provider.stream(messages, **extra):
                    if not chunk:
                        continue
                    pieces.append(chunk)
                    yield {"type": "delta", "text": chunk}
            except LLMError as exc:
                # 真实模型不可用时自动降级为 mock，保证不中断对话
                yield {
                    "type": "notice",
                    "level": "warn",
                    "message": f"真实模型调用失败，已降级为演示模式：{exc}",
                }
                active_provider = MockProvider()
                async for chunk in active_provider.stream(messages, **extra):
                    if not chunk:
                        continue
                    pieces.append(chunk)
                    yield {"type": "delta", "text": chunk}

            reply = "".join(pieces).strip() or "……"

            # 5) 落库 assistant 消息
            assistant_message = Message(session_id=session.id, role="assistant", content=reply)
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # 6) 状态演进
            state = update_state(session.mood, session.affection, user_text, reply)
            session.mood = state["mood"]
            session.affection = state["affection"]
            session.updated_at = datetime.now()
            db.commit()
            yield {"type": "meta", "mood": session.mood, "affection": session.affection}

            # 7) 记忆反思
            reflect_result: Dict[str, Any] = {"triggered": False, "added": 0}
            try:
                reflect_result = await maybe_reflect(
                    db,
                    session,
                    llm=active_provider,
                    reflect_every=reflect_every,
                    recent_window=max(6, recent_window),
                )
            except Exception as exc:  # 反思失败不影响对话
                yield {"type": "notice", "level": "warn", "message": f"记忆反思跳过：{exc}"}

            yield {
                "type": "done",
                "message_id": assistant_message.id,
                "user_message_id": user_message.id,
                "mood": session.mood,
                "affection": session.affection,
                "memory_added": int(reflect_result.get("added") or 0),
                "memories": memory_texts,
                "content": reply,
                "lore": injection_summary(lore_hits),
            }
        finally:
            if owns_db:
                db.close()


def to_sse(event: Dict[str, Any]) -> str:
    """把事件字典编码成 SSE 报文。"""
    kind = str(event.get("type") or "message")
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {kind}\ndata: {payload}\n\n"


async def stream_reply(session_id: int, user_text: str, use_memory: bool = True, db=None):
    """模块级便捷入口。"""
    engine = ChatEngine(db=db)
    async for event in engine.stream_reply(session_id, user_text, use_memory=use_memory):
        yield event


__all__ = ["ChatEngine", "apply_feedback_to_state", "stream_reply", "to_sse", "update_state"]
