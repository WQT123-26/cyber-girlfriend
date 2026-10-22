"""人格相关 API：增删改查 + 从导入批次生成人格 + 提示词预览。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.models import (
    ChatSession,
    Feedback,
    ImportBatch,
    Memory,
    Message,
    Persona,
    WorldBookEntry,
)
from app.schemas.schemas import (
    GeneratePersonaIn,
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
    PromptPreviewIn,
    PromptPreviewOut,
)
from app.services.persona.extractor import DEFAULT_SLIDERS, extract_from_messages
from app.services.persona.prompt import (
    build_greeting,
    build_persona_summary_text,
    build_system_prompt,
)

router = APIRouter(prefix="/personas", tags=["personas"])


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def normalize_sliders(source: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """补齐 5 个维度并夹紧到 0~100。"""
    result: Dict[str, int] = {}
    source = source or {}
    for key, default in DEFAULT_SLIDERS.items():
        try:
            value = int(float(source.get(key, default)))
        except (TypeError, ValueError):
            value = default
        result[key] = max(0, min(100, value))
    return result


def persona_to_dict(persona: Persona, summary_text: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": persona.id,
        "name": persona.name,
        "avatar_emoji": persona.avatar_emoji,
        "relation": persona.relation,
        "nickname_for_user": persona.nickname_for_user,
        "sliders": persona.slider_dict(),
        "persona_card": persona.card(),
        "greeting": persona.greeting,
        "source": persona.source,
        # ---- 角色卡元信息（供前端展示 / 导出）----
        "creator_notes": getattr(persona, "creator_notes", "") or "",
        "tags": persona.tag_list() if hasattr(persona, "tag_list") else [],
        "character_version": getattr(persona, "character_version", "") or "",
        "card_spec": getattr(persona, "card_spec", "") or "",
        "created_at": persona.created_at,
        "summary_text": summary_text if summary_text is not None else build_persona_summary_text(persona),
    }


def get_persona_or_404(db: Session, persona_id: int) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="人格不存在")
    return persona


# --------------------------------------------------------------------------
# 静态路径（必须声明在 /{persona_id} 之前）
# --------------------------------------------------------------------------
@router.post("/generate", response_model=PersonaOut)
def generate_persona(payload: GeneratePersonaIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """从导入批次中提取人格卡与滑块，并保存为新人格。"""
    batch = db.get(ImportBatch, payload.import_batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    messages = batch.message_list()
    if not messages:
        raise HTTPException(status_code=400, detail="该批次没有可用的消息数据")

    speakers = {item.get("name") for item in batch.speaker_list()}
    if payload.speaker not in speakers:
        raise HTTPException(status_code=400, detail=f"发言人「{payload.speaker}」不在该批次中")

    extracted = extract_from_messages(messages, payload.speaker, display_name=payload.name or payload.speaker)
    card = extracted["persona_card"]
    sliders = normalize_sliders(extracted["sliders"])

    persona = Persona(
        name=payload.name or payload.speaker,
        avatar_emoji=payload.avatar_emoji or "💫",
        relation=payload.relation or "女友",
        nickname_for_user=payload.nickname_for_user or "你",
        source="imported",
    )
    persona.set_card(card)
    persona.set_sliders(sliders)
    persona.greeting = build_greeting(persona)
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona_to_dict(persona)


@router.post("/preview-prompt", response_model=PromptPreviewOut)
def preview_prompt(payload: PromptPreviewIn) -> Dict[str, Any]:
    """人设编辑页右侧的实时提示词预览（不落库）。"""
    data = payload.persona
    card = dict(data.persona_card or {})
    sliders = normalize_sliders(data.sliders)
    persona_like: Dict[str, Any] = {
        "name": data.name,
        "relation": data.relation,
        "nickname_for_user": data.nickname_for_user,
        "persona_card": card,
        "sliders": sliders,
        "greeting": data.greeting,
    }
    demo_memories = ["用户喜欢在深夜聊天", "用户最近在准备换工作，压力有点大"]
    system_prompt = build_system_prompt(
        persona_like,
        user_nickname=data.nickname_for_user,
        mood=72,
        affection=58,
        memories=demo_memories,
    )
    return {
        "system_prompt": system_prompt,
        "greeting": build_greeting(persona_like),
        "summary_text": build_persona_summary_text(persona_like),
    }


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
@router.get("", response_model=List[PersonaOut])
def list_personas(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.query(Persona).order_by(Persona.id.asc()).all()
    return [persona_to_dict(item) for item in rows]


@router.post("", response_model=PersonaOut)
def create_persona(payload: PersonaCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    persona = Persona(
        name=payload.name or "未命名",
        avatar_emoji=payload.avatar_emoji or "🌸",
        relation=payload.relation or "女友",
        nickname_for_user=payload.nickname_for_user or "你",
        greeting=payload.greeting or "",
        source="manual",
    )
    persona.set_card(payload.persona_card or {})
    persona.set_sliders(normalize_sliders(payload.sliders))
    persona.creator_notes = payload.creator_notes or ""
    persona.set_tag_list(payload.tags)
    persona.character_version = payload.character_version or ""
    persona.card_spec = payload.card_spec or ""
    if not persona.greeting:
        persona.greeting = build_greeting(persona)
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona_to_dict(persona)


@router.get("/{persona_id}", response_model=PersonaOut)
def get_persona(persona_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return persona_to_dict(get_persona_or_404(db, persona_id))


@router.put("/{persona_id}", response_model=PersonaOut)
def update_persona(persona_id: int, payload: PersonaUpdate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    persona = get_persona_or_404(db, persona_id)
    if payload.name is not None:
        persona.name = payload.name
    if payload.avatar_emoji is not None:
        persona.avatar_emoji = payload.avatar_emoji
    if payload.relation is not None:
        persona.relation = payload.relation
    if payload.nickname_for_user is not None:
        persona.nickname_for_user = payload.nickname_for_user
    if payload.greeting is not None:
        persona.greeting = payload.greeting
    if payload.sliders is not None:
        persona.set_sliders(normalize_sliders(payload.sliders))
    if payload.creator_notes is not None:
        persona.creator_notes = payload.creator_notes
    if payload.tags is not None:
        persona.set_tag_list(payload.tags)
    if payload.character_version is not None:
        persona.character_version = payload.character_version
    if payload.card_spec is not None:
        persona.card_spec = payload.card_spec
    if payload.persona_card is not None:
        card = dict(payload.persona_card)
        card["nickname"] = persona.name
        persona.set_card(card)
    db.commit()
    db.refresh(persona)
    return persona_to_dict(persona)


@router.delete("/{persona_id}")
def delete_persona(persona_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """删除人格，并级联清理其会话、消息、记忆与反馈样本。"""
    persona = get_persona_or_404(db, persona_id)

    session_ids = [row.id for row in db.query(ChatSession.id).filter(ChatSession.persona_id == persona_id).all()]
    if session_ids:
        db.query(Message).filter(Message.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.persona_id == persona_id).delete(synchronize_session=False)
    memory_count = db.query(Memory).filter(Memory.persona_id == persona_id).delete(synchronize_session=False)
    db.query(Feedback).filter(Feedback.persona_id == persona_id).delete(synchronize_session=False)
    worldbook_count = (
        db.query(WorldBookEntry).filter(WorldBookEntry.persona_id == persona_id).delete(synchronize_session=False)
    )
    db.delete(persona)
    db.commit()
    return {
        "ok": True,
        "deleted_persona_id": persona_id,
        "deleted_sessions": len(session_ids),
        "deleted_memories": int(memory_count or 0),
        "deleted_worldbook_entries": int(worldbook_count or 0),
    }


__all__ = ["router", "normalize_sliders", "persona_to_dict", "get_persona_or_404"]
