"""世界书 / Lorebook 匹配器。

职责：输入「最近 N 轮对话文本」+「某个 Persona 的世界书条目」，输出**本次应注入的条目列表**。

匹配规则
--------
1. **常驻条目**（``constant=True``）恒注入。
2. **关键词条目**：``keys`` 中任一关键词出现在扫描文本里即命中；
   ``case_sensitive=False`` 时统一转小写比较；``keys`` 为空的非常驻条目不注入。
3. 命中条目按 ``priority`` 降序排列（``priority`` 越大越先注入），
   同优先级按 ``id`` 升序，保证结果稳定可复现。
4. ``token_budget`` 约束：**用字符数近似 token**。
   ``budget<=0`` 表示不限；否则按上面的顺序累加，超出预算的条目跳过
   （记录在 ``skipped_budget`` 里），剩余预算不足下限时直接停止扫描。

注入位置（``position``）
------------------------
* ``before_char`` —— 插到 system prompt **之前**
* ``after_char``  —— 插到 system prompt **之后**
* ``at_depth``    —— 插到距消息列表末尾 ``depth`` 条消息之前

以上三种位置的落地逻辑见 ``inject_into_messages``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VALID_POSITIONS: Tuple[str, ...] = ("before_char", "after_char", "at_depth")
DEFAULT_POSITION = "before_char"
DEFAULT_DEPTH = 4
DEFAULT_SCAN_ROUNDS = 6
DEFAULT_SCAN_CHARS = 4000
MIN_USEFUL_BUDGET = 16  # 预算下限，低于此值不再继续扫描

BLOCK_TITLE = "【世界设定】（背景资料，理解即可；除非自然，不要直接复述）"


@dataclass
class LoreHit:
    """一条被判定为「本轮应注入」的世界书条目。"""

    entry_id: Optional[int]
    keys: List[str] = field(default_factory=list)
    content: str = ""
    position: str = DEFAULT_POSITION
    depth: int = DEFAULT_DEPTH
    priority: int = 100
    constant: bool = False
    matched_keys: List[str] = field(default_factory=list)
    cost: int = 0

    @property
    def reason(self) -> str:
        return "constant" if self.constant else "keyword"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "keys": list(self.keys),
            "content": self.content,
            "position": self.position,
            "depth": self.depth,
            "priority": self.priority,
            "constant": self.constant,
            "matched_keys": list(self.matched_keys),
            "cost": self.cost,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def normalize_position(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_POSITIONS else DEFAULT_POSITION


def estimate_tokens(text: Any) -> int:
    """字符数近似 token（中文 1 字≈1 token，英文会略高估，宁可保守）。"""
    return len(str(text or ""))


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _entry_view(entry: Any) -> Dict[str, Any]:
    """ORM 对象 / dict 统一成普通字典视图。"""
    if isinstance(entry, dict):
        keys = entry.get("keys")
        if isinstance(keys, str):
            keys = [item.strip() for item in keys.replace("，", ",").split(",") if item.strip()]
        return {
            "id": entry.get("id"),
            "keys": [str(item) for item in (keys or []) if str(item).strip()],
            "content": str(entry.get("content") or ""),
            "enabled": bool(entry.get("enabled", True)),
            "constant": bool(entry.get("constant", False)),
            "case_sensitive": bool(entry.get("case_sensitive", False)),
            "priority": _as_int(entry.get("priority"), 100),
            "position": entry.get("position"),
            "depth": _as_int(entry.get("depth"), DEFAULT_DEPTH),
            "token_budget": _as_int(entry.get("token_budget"), 0),
            "comment": str(entry.get("comment") or ""),
        }
    return {
        "id": getattr(entry, "id", None),
        "keys": entry.key_list() if hasattr(entry, "key_list") else [],
        "content": str(getattr(entry, "content", "") or ""),
        "enabled": bool(getattr(entry, "enabled", True)),
        "constant": bool(getattr(entry, "constant", False)),
        "case_sensitive": bool(getattr(entry, "case_sensitive", False)),
        "priority": _as_int(getattr(entry, "priority", 100), 100),
        "position": getattr(entry, "position", DEFAULT_POSITION),
        "depth": _as_int(getattr(entry, "depth", DEFAULT_DEPTH), DEFAULT_DEPTH),
        "token_budget": _as_int(getattr(entry, "token_budget", 0), 0),
        "comment": str(getattr(entry, "comment", "") or ""),
    }


def build_scan_text(
    messages: Optional[Iterable[Any]] = None,
    rounds: int = DEFAULT_SCAN_ROUNDS,
    max_chars: int = DEFAULT_SCAN_CHARS,
) -> str:
    """把最近 ``rounds`` 条消息拼成扫描文本（超长时保留靠后的内容）。"""
    texts: List[str] = []
    for item in messages or []:
        if isinstance(item, dict):
            role = str(item.get("role") or item.get("speaker") or "")
            content = str(item.get("content") or "")
        else:
            content = str(item or "")
            role = ""
        content = content.strip()
        if not content:
            continue
        texts.append(f"{role}: {content}" if role else content)

    window = max(1, int(rounds or DEFAULT_SCAN_ROUNDS))
    joined = "\n".join(texts[-window:])
    if max_chars and len(joined) > max_chars:
        joined = joined[-int(max_chars) :]
    return joined


def _matched_keys(view: Dict[str, Any], haystack: str, default_case_sensitive: Optional[bool]) -> List[str]:
    case_sensitive = view["case_sensitive"] if default_case_sensitive is None else bool(default_case_sensitive)
    needle = haystack if case_sensitive else haystack.lower()
    hits: List[str] = []
    for key in view["keys"]:
        candidate = key if case_sensitive else key.lower()
        if candidate and candidate in needle:
            hits.append(key)
    return hits


def match_entries(
    entries: Optional[Iterable[Any]],
    scan_text: Any,
    token_budget: int = 0,
    default_case_sensitive: Optional[bool] = None,
) -> Tuple[List[LoreHit], Dict[str, Any]]:
    """从 ``entries`` 中挑出本轮应注入的条目。

    返回 ``(命中列表, 统计)``；统计含候选数、命中数、因预算跳过的条目、估算总开销。
    """
    haystack = str(scan_text or "")
    budget = _as_int(token_budget, 0)
    views = [_entry_view(entry) for entry in (entries or [])]

    candidates: List[LoreHit] = []
    for view in views:
        if not view["enabled"]:
            continue
        content = view["content"].strip()
        if not content:
            continue
        if view["constant"]:
            matched: List[str] = []
        else:
            matched = _matched_keys(view, haystack, default_case_sensitive)
            if not matched:
                continue
        candidates.append(
            LoreHit(
                entry_id=view["id"],
                keys=list(view["keys"]),
                content=content,
                position=normalize_position(view["position"]),
                depth=max(0, view["depth"]),
                priority=view["priority"],
                constant=view["constant"],
                matched_keys=matched,
                cost=estimate_tokens(content),
            )
        )

    candidates.sort(key=lambda hit: (-hit.priority, hit.entry_id if hit.entry_id is not None else 0))

    hits: List[LoreHit] = []
    skipped_budget: List[Dict[str, Any]] = []
    used = 0
    for hit in candidates:
        if budget > 0:
            if used + hit.cost > budget:
                skipped_budget.append({"entry_id": hit.entry_id, "cost": hit.cost, "priority": hit.priority})
                continue
            used += hit.cost
        hits.append(hit)

    stats = {
        "candidates": len(candidates),
        "injected": len(hits),
        "budget": budget,
        "used": used,
        "skipped_budget": skipped_budget,
        "constant_injected": sum(1 for hit in hits if hit.constant),
        "keyword_injected": sum(1 for hit in hits if not hit.constant),
    }
    return hits, stats


# --------------------------------------------------------------------------
# 数据库接入
# --------------------------------------------------------------------------
def load_entries(db: Any, persona_id: int, enabled_only: bool = True) -> List[Any]:
    """读取某人格的世界书条目。"""
    from app.models.models import WorldBookEntry

    query = db.query(WorldBookEntry).filter(WorldBookEntry.persona_id == persona_id)
    if enabled_only:
        query = query.filter(WorldBookEntry.enabled.is_(True))
    return query.order_by(WorldBookEntry.priority.desc(), WorldBookEntry.id.asc()).all()


def collect_hits(
    db: Any,
    persona_id: int,
    messages: Optional[Iterable[Any]] = None,
    rounds: Optional[int] = None,
    token_budget: Optional[int] = None,
    case_sensitive: Optional[bool] = None,
) -> Tuple[List[LoreHit], Dict[str, Any]]:
    """便捷入口：按运行时配置读取条目并完成匹配。"""
    from app.core.config import get_runtime_config

    cfg = get_runtime_config(db) if db is not None else {}
    entry_list = load_entries(db, persona_id) if db is not None else []
    scan = build_scan_text(
        messages,
        rounds=_as_int(rounds if rounds is not None else cfg.get("lore_scan_window"), DEFAULT_SCAN_ROUNDS),
    )
    budget = _as_int(token_budget if token_budget is not None else cfg.get("lore_budget"), 0)
    hits, stats = match_entries(entry_list, scan, token_budget=budget, default_case_sensitive=case_sensitive)
    stats["scan_chars"] = len(scan)
    return hits, stats


# --------------------------------------------------------------------------
# 注入
# --------------------------------------------------------------------------
def split_by_position(hits: Optional[Iterable[LoreHit]]) -> Dict[str, List[LoreHit]]:
    groups: Dict[str, List[LoreHit]] = {position: [] for position in VALID_POSITIONS}
    for hit in hits or []:
        groups[normalize_position(hit.position)].append(hit)
    return groups


def render_block(hits: Optional[Iterable[LoreHit]], title: str = BLOCK_TITLE) -> str:
    """把一组条目渲染成一段可直接作为 system 消息的文本。"""
    lines: List[str] = []
    for hit in hits or []:
        content = str(hit.content or "").strip()
        if content:
            lines.append(f"- {content}")
    if not lines:
        return ""
    return "\n".join([title, *lines])


def inject_into_messages(
    messages: Sequence[Dict[str, Any]],
    hits: Optional[Iterable[LoreHit]],
    default_depth: int = DEFAULT_DEPTH,
) -> List[Dict[str, Any]]:
    """按 ``position`` 把世界书条目插入消息列表，返回**新列表**（不修改入参）。

    三种位置：
        * before_char —— 列表最前面（system prompt 之前）
        * after_char  —— 首条 system 之后（system prompt 之后）
        * at_depth    —— 距末尾 ``depth`` 条消息之前（depth 越大越靠前）
    """
    original = [dict(item) for item in (messages or [])]
    groups = split_by_position(hits)

    # at_depth：按 depth 分组，depth 小者更靠近末尾
    depth_groups: Dict[int, List[LoreHit]] = {}
    for hit in groups["at_depth"]:
        depth = hit.depth if hit.depth > 0 else max(0, int(default_depth or DEFAULT_DEPTH))
        depth_groups.setdefault(depth, []).append(hit)

    total = len(original)
    insert_map: Dict[int, List[LoreHit]] = {}
    for depth, items in depth_groups.items():
        index = total - max(1, depth)
        index = max(1, min(index, total))  # 至少排在 system prompt 之后
        insert_map.setdefault(index, []).extend(items)

    result: List[Dict[str, Any]] = []
    before_block = render_block(groups["before_char"])
    after_block = render_block(groups["after_char"])
    if before_block:
        result.append({"role": "system", "content": before_block})

    for index, message in enumerate(original):
        pending = insert_map.get(index)
        if pending:
            block = render_block(pending)
            if block:
                result.append({"role": "system", "content": block})
        result.append(message)
        if index == 0 and after_block:
            result.append({"role": "system", "content": after_block})

    # 边界：消息列表为空时，after_char 块仍要落地
    if total == 0 and after_block:
        result.append({"role": "system", "content": after_block})
    return result


def injection_summary(hits: Optional[Iterable[LoreHit]]) -> Dict[str, Any]:
    """给前端 / SSE notice 用的精简注入信息。"""
    hit_list = list(hits or [])
    return {
        "count": len(hit_list),
        "constant": sum(1 for hit in hit_list if hit.constant),
        "keyword": sum(1 for hit in hit_list if not hit.constant),
        "positions": {
            position: sum(1 for hit in hit_list if normalize_position(hit.position) == position)
            for position in VALID_POSITIONS
        },
        "comments": [str(hit.content)[:24] for hit in hit_list[:5]],
    }


__all__ = [
    "BLOCK_TITLE",
    "DEFAULT_DEPTH",
    "DEFAULT_SCAN_ROUNDS",
    "LoreHit",
    "VALID_POSITIONS",
    "build_scan_text",
    "collect_hits",
    "estimate_tokens",
    "inject_into_messages",
    "injection_summary",
    "load_entries",
    "match_entries",
    "normalize_position",
    "render_block",
    "split_by_position",
]
