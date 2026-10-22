"""会话 API：创建 / 列表 / 详情 / 删除 / 消息列表。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.personas import get_persona_or_404
from app.db.base import get_db
from app.models.models import ChatSession, Message, Persona
from app.schemas.schemas import MessageOut, SessionCreate, SessionOut
from app.services.persona.prompt import build_greeting

router = APIRouter(prefix="/sessions", tags=["sessions"])


def session_to_dict(db: Session, session: ChatSession) -> Dict[str, Any]:
    persona = db.get(Persona, session.persona_id)
    message_count = (
        db.query(func.count(Message.id)).filter(Message.session_id == session.id).scalar() or 0
    )
    last = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.id.desc())
        .first()
    )
    return {
        "id": session.id,
        "persona_id": session.persona_id,
        "persona_name": persona.name if persona else "（已删除）",
        "persona_emoji": persona.avatar_emoji if persona else "❓",
        "title": session.title,
        "mood": session.mood,
        "affection": session.affection,
        "summary": session.summary or "",
        "message_count": int(message_count),
        "last_message": (last.content[:60] if last else ""),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def message_to_dict(message: Message) -> Dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "feedback": message.feedback,
        "rewritten": bool(message.rewritten),
        "created_at": message.created_at,
    }


@router.post("", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    persona = get_persona_or_404(db, payload.persona_id)
    session = ChatSession(
        persona_id=persona.id,
        title=payload.title or f"与{persona.name}的对话",
        mood=70,
        affection=50,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 首条消息即开场白，保证聊天页打开就有内容
    greeting = (persona.greeting or "").strip() or build_greeting(persona)
    db.add(Message(session_id=session.id, role="assistant", content=greeting))
    db.commit()
    return session_to_dict(db, session)


@router.get("", response_model=List[SessionOut])
def list_sessions(
    persona_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    query = db.query(ChatSession)
    if persona_id:
        query = query.filter(ChatSession.persona_id == persona_id)
    rows = query.order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()).limit(200).all()
    return [session_to_dict(db, item) for item in rows]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_to_dict(db, session)


@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    deleted = db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    return {"ok": True, "deleted_session_id": session_id, "deleted_messages": int(deleted or 0)}


@router.get("/{session_id}/messages", response_model=List[MessageOut])
def list_messages(
    session_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.asc())
        .limit(limit)
        .all()
    )
    return [message_to_dict(item) for item in rows]


__all__ = ["router", "message_to_dict", "session_to_dict"]
