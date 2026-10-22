"""长期记忆存储与召回。

打分公式::

    score = 词法相似度(TF-IDF 余弦) × 时间衰减(半衰期 30 天) × (0.5 + 0.5 × importance)

* 中文按 **字符 bigram** 切分，英文/数字按词切分，统一用正则 ``[\\u4e00-\\u9fa5a-zA-Z0-9]+`` 抓取片段；
* 召回后会更新 ``last_access_at`` 与 ``access_count``（用进废退）。
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from app.models.models import Memory

_TOKEN = re.compile(r"[\u4e00-\u9fa5a-zA-Z0-9]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fa5]+")
_WORD_RUN = re.compile(r"[a-zA-Z0-9]+")
_CJK_ONLY = re.compile(r"^[\u4e00-\u9fa5]+$")

HALF_LIFE_DAYS = 30.0
MEMORY_KINDS = ("fact", "preference", "event", "promise")


# --------------------------------------------------------------------------
# 分词与相似度
# --------------------------------------------------------------------------
def tokenize(text: str) -> List[str]:
    """中文 bigram + 英文/数字词，自研实现（不依赖 jieba）。"""
    tokens: List[str] = []
    for chunk in _TOKEN.findall(text or ""):
        for run in _CJK_RUN.findall(chunk):
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        for word in _WORD_RUN.findall(chunk):
            if _CJK_ONLY.match(word):
                continue
            tokens.append(word.lower())
    return tokens


def _term_freq(tokens: List[str]) -> Dict[str, int]:
    counter: Dict[str, int] = {}
    for token in tokens:
        counter[token] = counter.get(token, 0) + 1
    return counter


def _build_idf(docs: List[List[str]]) -> Dict[str, float]:
    total = len(docs)
    df: Dict[str, int] = {}
    for tokens in docs:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    return {token: math.log((total + 1.0) / (count + 1.0)) + 1.0 for token, count in df.items()}


def _cosine(left: List[str], right: List[str], idf: Dict[str, float]) -> float:
    left_tf = _term_freq(left)
    right_tf = _term_freq(right)
    if not left_tf or not right_tf:
        return 0.0
    shared = set(left_tf) & set(right_tf)
    if not shared:
        return 0.0

    def weight(tf: Dict[str, int], token: str) -> float:
        return tf[token] * idf.get(token, 1.0)

    numerator = sum(weight(left_tf, t) * weight(right_tf, t) for t in shared)
    left_norm = math.sqrt(sum(weight(left_tf, t) ** 2 for t in left_tf))
    right_norm = math.sqrt(sum(weight(right_tf, t) ** 2 for t in right_tf))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _decay(reference: Optional[datetime], now: Optional[datetime] = None) -> float:
    now = now or datetime.now()
    if reference is None:
        return 1.0
    age_days = max(0.0, (now - reference).total_seconds() / 86400.0)
    return math.pow(0.5, age_days / HALF_LIFE_DAYS)


def _clamp_importance(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
def add_memory(
    db,
    persona_id: int,
    content: str,
    kind: str = "fact",
    importance: float = 0.5,
    source: str = "reflect",
    session_id: Optional[int] = None,
) -> Optional[Memory]:
    content = str(content or "").strip()
    if not content:
        return None
    if kind not in MEMORY_KINDS:
        kind = "fact"
    duplicated = (
        db.query(Memory)
        .filter(Memory.persona_id == persona_id, Memory.content == content)
        .first()
    )
    if duplicated is not None:
        duplicated.importance = max(duplicated.importance, _clamp_importance(importance))
        duplicated.last_access_at = datetime.now()
        db.commit()
        return duplicated

    memory = Memory(
        persona_id=persona_id,
        session_id=session_id,
        content=content,
        kind=kind,
        importance=_clamp_importance(importance),
        source=source or "reflect",
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def list_memories(
    db,
    persona_id: Optional[int] = None,
    kind: Optional[str] = None,
    limit: int = 500,
) -> List[Memory]:
    query = db.query(Memory)
    if persona_id:
        query = query.filter(Memory.persona_id == persona_id)
    if kind:
        query = query.filter(Memory.kind == kind)
    return query.order_by(Memory.created_at.desc(), Memory.id.desc()).limit(limit).all()


def get_memory(db, memory_id: int) -> Optional[Memory]:
    return db.query(Memory).filter(Memory.id == memory_id).first()


def update_memory(db, memory_id: int, **fields: Any) -> Optional[Memory]:
    memory = get_memory(db, memory_id)
    if memory is None:
        return None
    if fields.get("content"):
        memory.content = str(fields["content"]).strip()
    if fields.get("kind") in MEMORY_KINDS:
        memory.kind = fields["kind"]
    if fields.get("importance") is not None:
        memory.importance = _clamp_importance(fields["importance"])
    db.commit()
    db.refresh(memory)
    return memory


def delete_memory(db, memory_id: int) -> bool:
    memory = get_memory(db, memory_id)
    if memory is None:
        return False
    db.delete(memory)
    db.commit()
    return True


# --------------------------------------------------------------------------
# 召回
# --------------------------------------------------------------------------
def retrieve_scored(
    db,
    persona_id: int,
    query: str,
    top_k: int = 5,
    touch: bool = True,
) -> List[Tuple[Memory, float]]:
    """返回 (记忆, 分数) 列表，按分数降序。"""
    memories: List[Memory] = (
        db.query(Memory)
        .filter(Memory.persona_id == persona_id)
        .order_by(Memory.id.desc())
        .limit(1000)
        .all()
    )
    if not memories:
        return []

    query = str(query or "").strip()
    if not query:
        ranked = sorted(memories, key=lambda m: (m.importance, m.created_at), reverse=True)
        chosen = [(m, float(m.importance or 0.0)) for m in ranked[: max(1, top_k)]]
        if touch:
            _touch(db, [m for m, _ in chosen])
        return chosen

    query_tokens = tokenize(query)
    doc_tokens = [tokenize(m.content) for m in memories]
    idf = _build_idf([query_tokens] + doc_tokens)

    now = datetime.now()
    scored: List[Tuple[Memory, float]] = []
    for memory, tokens in zip(memories, doc_tokens):
        similarity = _cosine(query_tokens, tokens, idf)
        if similarity <= 0:
            continue
        decay = _decay(memory.last_access_at or memory.created_at, now)
        importance = _clamp_importance(memory.importance)
        score = similarity * decay * (0.5 + 0.5 * importance)
        scored.append((memory, score))

    scored.sort(key=lambda item: (-item[1], -item[0].id))
    top_k = max(1, int(top_k or 5))
    chosen = scored[:top_k]
    if touch:
        _touch(db, [m for m, _ in chosen])
    return chosen


def retrieve(db, persona_id: int, query: str, top_k: int = 5) -> List[Memory]:
    """召回记忆（按打分排序），并更新访问时间与次数。"""
    return [memory for memory, _ in retrieve_scored(db, persona_id, query, top_k, touch=True)]


def _touch(db, memories: List[Memory]) -> None:
    if not memories:
        return
    now = datetime.now()
    for memory in memories:
        memory.last_access_at = now
        memory.access_count = int(memory.access_count or 0) + 1
    db.commit()


__all__ = [
    "HALF_LIFE_DAYS",
    "MEMORY_KINDS",
    "add_memory",
    "delete_memory",
    "get_memory",
    "list_memories",
    "retrieve",
    "retrieve_scored",
    "tokenize",
    "update_memory",
]
