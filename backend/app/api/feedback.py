"""消息反馈 API：点赞 / 踩 / 改写。

* ``like`` / ``dislike`` 会写入 ``feedbacks`` 表并微调会话的 mood / affection；
* ``rewrite`` 会用新文本覆盖该条 assistant 消息（``rewritten=True``），
  并把「原回复 → 用户期望回复」作为偏好样本落库，供后续偏好学习使用。
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.models import ChatSession, Feedback, Message
from app.schemas.schemas import FeedbackIn, FeedbackOut
from app.services.chat.engine import apply_feedback_to_state

router = APIRouter(tags=["feedback"])

VALID_ACTIONS = ("like", "dislike", "rewrite")


@router.post("/messages/{message_id}/feedback", response_model=FeedbackOut)
def submit_feedback(
    message_id: int,
    payload: FeedbackIn,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    action = (payload.action or "").strip()
    if action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action 只能是 {VALID_ACTIONS}")

    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="只能对 AI 回复进行反馈")

    original = message.content
    new_content = (payload.content or "").strip()
    if action == "rewrite" and not new_content:
        raise HTTPException(status_code=400, detail="改写内容不能为空")

    if action == "like":
        message.feedback = 1
    elif action == "dislike":
        message.feedback = -1
    else:
        message.content = new_content
        message.rewritten = True

    persona_id = (
        db.query(ChatSession.persona_id).filter(ChatSession.id == message.session_id).scalar()
    )
    db.add(
        Feedback(
            message_id=message.id,
            session_id=message.session_id,
            persona_id=persona_id,
            action=action,
            original=original,
            revised=new_content if action == "rewrite" else str(getattr(payload, "note", "") or ""),
        )
    )
    db.commit()
    db.refresh(message)

    state: Dict[str, int] = {"mood": 0, "affection": 0}
    session = db.get(ChatSession, message.session_id)
    if session is not None:
        state = apply_feedback_to_state(session.mood, session.affection, action)
        session.mood = state["mood"]
        session.affection = state["affection"]
        db.commit()

    return {
        "ok": True,
        "action": action,
        "message_id": message.id,
        "content": message.content,
        "feedback": message.feedback,
        "rewritten": bool(message.rewritten),
        "mood": state["mood"],
        "affection": state["affection"],
    }


@router.get("/messages/{message_id}/feedback")
def list_message_feedback(message_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = (
        db.query(Feedback)
        .filter(Feedback.message_id == message_id)
        .order_by(Feedback.id.desc())
        .limit(50)
        .all()
    )
    return {
        "message_id": message_id,
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "original": row.original,
                "content": row.revised,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


__all__ = ["router"]
