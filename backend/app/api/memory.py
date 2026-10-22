"""长期记忆 API：列表 / 新增 / 修改 / 删除 / 检索测试。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.models import Memory
from app.schemas.schemas import MemoryCreate, MemoryOut, MemorySearchIn, MemorySearchOut, MemoryUpdate
from app.services.memory.store import (
    MEMORY_KINDS,
    add_memory,
    delete_memory,
    list_memories,
    retrieve_scored,
    update_memory,
)

router = APIRouter(prefix="/memories", tags=["memories"])


def memory_to_dict(memory: Memory) -> Dict[str, Any]:
    return {
        "id": memory.id,
        "persona_id": memory.persona_id,
        "session_id": memory.session_id,
        "content": memory.content,
        "kind": memory.kind,
        "importance": memory.importance,
        "source": memory.source,
        "access_count": memory.access_count,
        "created_at": memory.created_at,
        "last_access_at": memory.last_access_at,
    }


@router.get("", response_model=List[MemoryOut])
def get_memories(
    persona_id: Optional[int] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    rows = list_memories(db, persona_id=persona_id, kind=kind)
    return [memory_to_dict(item) for item in rows]


@router.post("", response_model=MemoryOut)
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    if payload.kind not in MEMORY_KINDS:
        raise HTTPException(status_code=400, detail=f"kind 只能是 {MEMORY_KINDS}")
    memory = add_memory(
        db,
        persona_id=payload.persona_id,
        content=payload.content,
        kind=payload.kind or "fact",
        importance=payload.importance if payload.importance is not None else 0.6,
        source="manual",
        session_id=payload.session_id,
    )
    if memory is None:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    return memory_to_dict(memory)


@router.post("/search", response_model=MemorySearchOut)
def search_memories(payload: MemorySearchIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """记忆检索测试：验证召回打分效果。"""
    scored = retrieve_scored(
        db,
        persona_id=payload.persona_id,
        query=payload.query,
        top_k=payload.top_k or 5,
        touch=False,
    )
    return {
        "query": payload.query,
        "persona_id": payload.persona_id,
        "count": len(scored),
        "items": [
            {"score": round(float(score), 4), "memory": memory_to_dict(memory)}
            for memory, score in scored
        ],
    }


@router.put("/{memory_id}", response_model=MemoryOut)
def modify_memory(memory_id: int, payload: MemoryUpdate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    if payload.kind is not None and payload.kind not in MEMORY_KINDS:
        raise HTTPException(status_code=400, detail=f"kind 只能是 {MEMORY_KINDS}")
    memory = update_memory(
        db,
        memory_id,
        content=payload.content,
        kind=payload.kind,
        importance=payload.importance,
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory_to_dict(memory)


@router.delete("/{memory_id}")
def remove_memory(memory_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    if not delete_memory(db, memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True, "deleted_memory_id": memory_id}


__all__ = ["router", "memory_to_dict"]
