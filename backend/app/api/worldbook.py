"""世界书 / Lorebook CRUD API。

路径（挂载后前缀为 ``/api``）：
    GET    /personas/{persona_id}/worldbook            列出某人格的世界书条目
    POST   /personas/{persona_id}/worldbook            新建条目
    POST   /personas/{persona_id}/worldbook/preview     调试：给一段文本看命中情况
    PUT    /worldbook/{entry_id}                       更新条目
    DELETE /worldbook/{entry_id}                       删除条目

注入规则与匹配算法见 ``app.services.lore.matcher``；本模块只负责持久化与参数校验。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.models import Persona, WorldBookEntry
from app.schemas.schemas import (
    WorldBookEntryIn,
    WorldBookEntryOut,
    WorldBookEntryUpdate,
    WorldBookListOut,
    WorldBookPreviewIn,
    WorldBookPreviewOut,
)
from app.services.lore.matcher import match_entries, normalize_position

router = APIRouter(tags=["worldbook"])

MAX_PRIORITY = 100000
MAX_DEPTH = 64
MAX_BUDGET = 100000


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clamp_int(value: Any, default: int, low: int = 0, high: int = MAX_PRIORITY) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_keys(value: Any) -> List[str]:
    """关键词列表归一化：去空白、去重、保持原顺序。"""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace("，", ",").replace("\n", ",").split(",")
    else:
        raw = list(value)
    result: List[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def entry_to_dict(entry: WorldBookEntry) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "persona_id": entry.persona_id,
        "keys": entry.key_list(),
        "content": entry.content or "",
        "enabled": bool(entry.enabled),
        "constant": bool(entry.constant),
        "case_sensitive": bool(entry.case_sensitive),
        "priority": int(entry.priority or 0),
        "position": normalize_position(entry.position),
        "depth": int(entry.depth or 0),
        "token_budget": int(entry.token_budget or 0),
        "comment": entry.comment or "",
        "source": getattr(entry, "source", "manual") or "manual",
        "created_at": entry.created_at,
    }


def get_persona_or_404(db: Session, persona_id: int) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="人格不存在")
    return persona


def get_entry_or_404(db: Session, entry_id: int) -> WorldBookEntry:
    entry = db.get(WorldBookEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="世界书条目不存在")
    return entry


# --------------------------------------------------------------------------
# 人格维度：列表 / 新建 / 命中预览
# --------------------------------------------------------------------------
@router.get("/personas/{persona_id}/worldbook", response_model=WorldBookListOut)
def list_worldbook(persona_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    get_persona_or_404(db, persona_id)
    rows = (
        db.query(WorldBookEntry)
        .filter(WorldBookEntry.persona_id == persona_id)
        .order_by(WorldBookEntry.priority.desc(), WorldBookEntry.id.asc())
        .all()
    )
    return {"persona_id": persona_id, "count": len(rows), "entries": [entry_to_dict(row) for row in rows]}


@router.post("/personas/{persona_id}/worldbook", response_model=WorldBookEntryOut)
def create_worldbook_entry(
    persona_id: int,
    payload: WorldBookEntryIn,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    get_persona_or_404(db, persona_id)
    content = (payload.content or "").strip()
    keys = normalize_keys(payload.keys)
    if not content:
        raise HTTPException(status_code=400, detail="条目内容不能为空")
    if not payload.constant and not keys:
        raise HTTPException(status_code=400, detail="非常驻条目必须至少填写一个关键词")

    entry = WorldBookEntry(
        persona_id=persona_id,
        content=content,
        enabled=bool(payload.enabled),
        constant=bool(payload.constant),
        case_sensitive=bool(payload.case_sensitive),
        priority=_clamp_int(payload.priority, 100, 0, MAX_PRIORITY),
        position=normalize_position(payload.position),
        depth=_clamp_int(payload.depth, 4, 0, MAX_DEPTH),
        token_budget=_clamp_int(payload.token_budget, 0, 0, MAX_BUDGET),
        comment=(payload.comment or "").strip()[:128],
        source="manual",
    )
    entry.set_key_list(keys)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry_to_dict(entry)


@router.post("/personas/{persona_id}/worldbook/preview", response_model=WorldBookPreviewOut)
def preview_worldbook(
    persona_id: int,
    payload: WorldBookPreviewIn,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """用一段文本试跑匹配，便于前端调试「哪些条目会被注入」。"""
    get_persona_or_404(db, persona_id)
    rows = (
        db.query(WorldBookEntry)
        .filter(WorldBookEntry.persona_id == persona_id)
        .order_by(WorldBookEntry.priority.desc(), WorldBookEntry.id.asc())
        .all()
    )
    hits, stats = match_entries(rows, payload.text or "", token_budget=payload.token_budget or 0)
    return {
        "persona_id": persona_id,
        "scan_text": payload.text or "",
        "count": len(hits),
        "stats": stats,
        "items": [hit.to_dict() for hit in hits],
    }


# --------------------------------------------------------------------------
# 条目维度：更新 / 删除
# --------------------------------------------------------------------------
@router.put("/worldbook/{entry_id}", response_model=WorldBookEntryOut)
def update_worldbook_entry(
    entry_id: int,
    payload: WorldBookEntryUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    entry = get_entry_or_404(db, entry_id)

    if payload.keys is not None:
        entry.set_key_list(normalize_keys(payload.keys))
    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="条目内容不能为空")
        entry.content = content
    if payload.enabled is not None:
        entry.enabled = bool(payload.enabled)
    if payload.constant is not None:
        entry.constant = bool(payload.constant)
    if payload.case_sensitive is not None:
        entry.case_sensitive = bool(payload.case_sensitive)
    if payload.priority is not None:
        entry.priority = _clamp_int(payload.priority, entry.priority, 0, MAX_PRIORITY)
    if payload.position is not None:
        entry.position = normalize_position(payload.position)
    if payload.depth is not None:
        entry.depth = _clamp_int(payload.depth, entry.depth, 0, MAX_DEPTH)
    if payload.token_budget is not None:
        entry.token_budget = _clamp_int(payload.token_budget, entry.token_budget, 0, MAX_BUDGET)
    if payload.comment is not None:
        entry.comment = payload.comment.strip()[:128]

    if not entry.constant and not entry.key_list():
        raise HTTPException(status_code=400, detail="非常驻条目必须至少保留一个关键词")

    db.commit()
    db.refresh(entry)
    return entry_to_dict(entry)


@router.delete("/worldbook/{entry_id}")
def delete_worldbook_entry(entry_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    entry = get_entry_or_404(db, entry_id)
    persona_id = entry.persona_id
    db.delete(entry)
    db.commit()
    return {"ok": True, "deleted_entry_id": entry_id, "persona_id": persona_id}


__all__ = ["entry_to_dict", "normalize_keys", "router"]
