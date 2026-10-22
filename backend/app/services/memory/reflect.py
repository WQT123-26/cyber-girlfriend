"""记忆反思：每隔 ``reflect_every`` 条 assistant 消息触发一次。

* LLM 可用时：让模型从最近对话里抽取 0~3 条事实，要求返回 JSON 数组，解析失败自动容错降级；
* LLM 不可用（mock 演示模式）时：用启发式句式规则直接抽取原句。

同时更新 ``session.summary``（LLM 可用时压缩，否则取最近若干轮拼接截断）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.models.models import Message
from app.services.memory.store import MEMORY_KINDS, add_memory

# ---- 启发式句式 ------------------------------------------------------------
_HEURISTIC_RULES = [
    (["我答应", "我保证", "我发誓", "我会记着", "说好了", "一定会"], "promise", 0.75),
    (
        ["我喜欢", "我超喜欢", "我最喜欢", "我很喜欢", "我爱吃", "我不吃", "我讨厌",
         "我不喜欢", "我受不了", "我习惯", "我更喜欢"],
        "preference",
        0.65,
    ),
    (
        ["我叫", "我的名字", "我是", "我住在", "我家在", "我生日", "我今年",
         "我在做", "我上班", "我在读", "我最近在", "我在学"],
        "fact",
        0.6,
    ),
    (["我想", "我打算", "我准备", "我计划", "下周", "明天我要"], "event", 0.55),
]

_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]+")

_REFLECT_PROMPT = """你是一个信息抽取器。请阅读下面这段对话，从「用户」说的话里抽取 0~3 条**关于用户本人的长期事实**。

要求：
1. 只抽取稳定、可长期复用的信息（姓名、居住地、职业、喜好、厌恶、重要承诺、重要事件）。
2. 不要抽取寒暄、提问、语气词、临时情绪。
3. 每条事实用一句简短的中文陈述，主语用「用户」。
4. 只输出 JSON 数组，不要输出任何解释或 Markdown 代码块。

JSON 格式：
[{{"content": "用户喜欢喝美式咖啡", "kind": "preference", "importance": 0.7}}]

kind 只能取：fact（客观事实）/ preference（喜好厌恶）/ event（经历事件）/ promise（约定承诺）
importance 取 0~1 的小数。

对话内容：
{conversation}
"""


def heuristic_extract(text: str, limit: int = 3) -> List[Dict[str, Any]]:
    """启发式抽取：命中句式直接把原句作为一条记忆。"""
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 3 or len(sentence) > 80:
            continue
        for keywords, kind, importance in _HEURISTIC_RULES:
            if any(word in sentence for word in keywords):
                if sentence in seen:
                    break
                seen.add(sentence)
                results.append({"content": sentence, "kind": kind, "importance": importance})
                break
        if len(results) >= limit:
            break
    return results


def _conversation_text(messages: List[Message]) -> str:
    lines: List[str] = []
    for message in messages:
        speaker = "用户" if message.role == "user" else "她"
        content = (message.content or "").strip()
        if content:
            lines.append(f"{speaker}：{content}")
    return "\n".join(lines)


def _parse_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    text = str(text or "").strip()
    if not text:
        return None
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, list):
        return None

    cleaned: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, str):
            item = {"content": item}
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        kind = str(item.get("kind") or "fact").strip()
        if kind not in MEMORY_KINDS:
            kind = "fact"
        try:
            importance = float(item.get("importance", 0.6))
        except (TypeError, ValueError):
            importance = 0.6
        cleaned.append(
            {"content": content, "kind": kind, "importance": max(0.0, min(1.0, importance))}
        )
    return cleaned


async def _extract_facts(llm, messages: List[Message]) -> List[Dict[str, Any]]:
    user_text = "\n".join(
        (m.content or "").strip() for m in messages if m.role == "user" and (m.content or "").strip()
    )
    if llm is not None and not getattr(llm, "is_demo", False):
        prompt = _REFLECT_PROMPT.format(conversation=_conversation_text(messages))
        try:
            raw = await llm.complete(
                [
                    {"role": "system", "content": "你是一个只输出 JSON 的信息抽取器。"},
                    {"role": "user", "content": prompt},
                ]
            )
            parsed = _parse_json_array(raw)
            if parsed is not None:
                return parsed[:3]
        except Exception:
            pass  # 任何失败都容错降级到启发式
    return heuristic_extract(user_text, limit=3)


async def _update_summary(llm, session, messages: List[Message]) -> str:
    conversation = _conversation_text(messages)
    previous = (getattr(session, "summary", "") or "").strip()
    if llm is not None and not getattr(llm, "is_demo", False):
        prompt = (
            "请把下面的对话压缩成不超过 80 字的中文摘要，保留关键事实与情绪走向，"
            "只输出摘要本身，不要任何前缀。\n\n" + conversation
        )
        try:
            raw = await llm.complete(
                [
                    {"role": "system", "content": "你是一个对话摘要器。"},
                    {"role": "user", "content": prompt},
                ]
            )
            summary = str(raw or "").strip()
            if summary:
                return summary[:400]
        except Exception:
            pass

    pieces: List[str] = []
    if previous:
        pieces.append(previous)
    pieces.append(conversation.replace("\n", " "))
    text = " ".join(pieces).strip()
    if len(text) > 300:
        text = "……" + text[-300:]
    return text


async def maybe_reflect(
    db,
    session,
    llm=None,
    reflect_every: int = 6,
    recent_window: int = 12,
) -> Dict[str, Any]:
    """到达触发阈值时执行一次记忆反思。返回执行详情。"""
    try:
        every = max(1, int(reflect_every))
    except (TypeError, ValueError):
        every = 6

    assistant_count = (
        db.query(func.count(Message.id))
        .filter(Message.session_id == session.id, Message.role == "assistant")
        .scalar()
        or 0
    )
    if assistant_count <= 0 or assistant_count % every != 0:
        return {"triggered": False, "added": 0, "summary": session.summary or ""}

    limit = max(6, int(recent_window or 12))
    rows = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()

    facts = await _extract_facts(llm, rows)
    added = 0
    for fact in facts:
        memory = add_memory(
            db,
            persona_id=session.persona_id,
            content=fact["content"],
            kind=fact["kind"],
            importance=fact["importance"],
            source="reflect",
            session_id=session.id,
        )
        if memory is not None:
            added += 1

    summary = await _update_summary(llm, session, rows)
    session.summary = summary
    db.commit()
    return {"triggered": True, "added": added, "summary": summary}


__all__ = ["heuristic_extract", "maybe_reflect"]
