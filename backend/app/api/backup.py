"""全量备份导出 / 导入。

路径（挂载后前缀为 ``/api``）：
    GET  /backup/export        导出全部数据为单个 JSON（密钥只出掩码）
    POST /backup/import        上传该 JSON 合并导入（幂等，按策略去重）

设计要点
--------
* **单文件**：一次请求拿到完整快照，便于用户自己留档 / 迁移机器。
* **密钥零泄露**：``llm_api_key`` 导出时用 ``mask_secret`` 打码；
  导入时**默认不接收**密钥（``import_api_key=false``），避免掩码串被写回数据库。
* **ID 追踪**：导入时记录 ``old_id -> new_id`` 映射（``persona_id`` / ``session_id`` /
  ``message_id``），子表外键随父表重映射，不会串数据。
* **策略可选**：``merge_by_id``（默认）/ ``merge_by_name`` / ``skip_duplicates``。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import CONFIG_KEYS, get_runtime_config, mask_secret, set_runtime_config
from app.db.base import get_db
from app.models.models import (
    AppConfig,
    ChatSession,
    Feedback,
    ImportBatch,
    Memory,
    Message,
    Persona,
    WorldBookEntry,
)

router = APIRouter(prefix="/backup", tags=["backup"])

FORMAT_NAME = "cyber_girlfriend_backup"
FORMAT_VERSION = 1
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
VALID_STRATEGIES = ("merge_by_id", "merge_by_name", "skip_duplicates")
# 导入时允许被写回的配置项（llm_api_key 单独受控，默认不动）
IMPORTABLE_SETTINGS = tuple(key for key in CONFIG_KEYS if key != "llm_api_key")
# 导出时一定不进文件的敏感键
ALWAYS_SECRET_KEYS = ("llm_api_key",)


# --------------------------------------------------------------------------
# 序列化工具
# --------------------------------------------------------------------------
def dt_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def dt_from_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------
def export_persona(persona: Persona) -> Dict[str, Any]:
    return {
        "id": persona.id,
        "name": persona.name,
        "avatar_emoji": persona.avatar_emoji,
        "relation": persona.relation,
        "nickname_for_user": persona.nickname_for_user,
        "persona_card": persona.card(),
        "sliders": persona.slider_dict(),
        "greeting": persona.greeting,
        "source": persona.source,
        "creator_notes": persona.creator_notes or "",
        "tags": persona.tag_list(),
        "character_version": persona.character_version or "",
        "card_spec": persona.card_spec or "",
        "extensions": persona.extension_dict(),
        "created_at": dt_to_iso(persona.created_at),
    }


def export_entry(entry: WorldBookEntry) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "persona_id": entry.persona_id,
        "keys": entry.key_list(),
        "content": entry.content or "",
        "enabled": bool(entry.enabled),
        "constant": bool(entry.constant),
        "case_sensitive": bool(entry.case_sensitive),
        "priority": int(entry.priority or 0),
        "position": entry.position or "before_char",
        "depth": int(entry.depth or 0),
        "token_budget": int(entry.token_budget or 0),
        "comment": entry.comment or "",
        "source": entry.source or "manual",
        "created_at": dt_to_iso(entry.created_at),
    }


def export_session(session: ChatSession) -> Dict[str, Any]:
    return {
        "id": session.id,
        "persona_id": session.persona_id,
        "title": session.title,
        "mood": int(session.mood or 0),
        "affection": int(session.affection or 0),
        "summary": session.summary or "",
        "created_at": dt_to_iso(session.created_at),
        "updated_at": dt_to_iso(session.updated_at),
    }


def export_message(message: Message) -> Dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content or "",
        "created_at": dt_to_iso(message.created_at),
        "feedback": int(message.feedback or 0),
        "rewritten": bool(message.rewritten),
    }


def export_memory(memory: Memory) -> Dict[str, Any]:
    return {
        "id": memory.id,
        "persona_id": memory.persona_id,
        "session_id": memory.session_id,
        "content": memory.content or "",
        "kind": memory.kind or "fact",
        "importance": float(memory.importance or 0.0),
        "source": memory.source or "reflect",
        "created_at": dt_to_iso(memory.created_at),
        "last_access_at": dt_to_iso(memory.last_access_at),
        "access_count": int(memory.access_count or 0),
    }


def export_feedback(row: Feedback) -> Dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "session_id": row.session_id,
        "persona_id": row.persona_id,
        "action": row.action,
        "original": row.original or "",
        "revised": row.revised or "",
        "created_at": dt_to_iso(row.created_at),
    }


def export_import_batch(row: ImportBatch) -> Dict[str, Any]:
    return {
        "id": row.id,
        "filename": row.filename,
        "fmt": row.fmt,
        "message_count": int(row.message_count or 0),
        "speakers": row.speaker_list(),
        "preview": row.preview_list(),
        "desensitize_enabled": bool(row.desensitize_enabled),
        "desensitize": row.stats_dict(),
        "created_at": dt_to_iso(row.created_at),
    }


def build_backup(db: Session, include_import_batches: bool = False, include_feedback: bool = True) -> Dict[str, Any]:
    """把全部业务数据组装成可序列化的 dict。"""
    personas = db.query(Persona).order_by(Persona.id.asc()).all()
    sessions = db.query(ChatSession).order_by(ChatSession.id.asc()).all()
    messages = db.query(Message).order_by(Message.id.asc()).all()
    memories = db.query(Memory).order_by(Memory.id.asc()).all()
    entries = db.query(WorldBookEntry).order_by(WorldBookEntry.id.asc()).all()

    messages_by_session: Dict[int, List[Dict[str, Any]]] = {}
    for message in messages:
        messages_by_session.setdefault(int(message.session_id), []).append(export_message(message))

    entries_by_persona: Dict[int, List[Dict[str, Any]]] = {}
    for entry in entries:
        entries_by_persona.setdefault(int(entry.persona_id), []).append(export_entry(entry))

    memories_by_persona: Dict[int, List[Dict[str, Any]]] = {}
    for memory in memories:
        memories_by_persona.setdefault(int(memory.persona_id), []).append(export_memory(memory))

    sessions_by_persona: Dict[int, List[Dict[str, Any]]] = {}
    for session in sessions:
        item = export_session(session)
        item["messages"] = messages_by_session.get(int(session.id), [])
        sessions_by_persona.setdefault(int(session.persona_id), []).append(item)

    persona_items: List[Dict[str, Any]] = []
    for persona in personas:
        item = export_persona(persona)
        item["worldbook"] = entries_by_persona.get(int(persona.id), [])
        item["memories"] = memories_by_persona.get(int(persona.id), [])
        item["sessions"] = sessions_by_persona.get(int(persona.id), [])
        persona_items.append(item)

    payload: Dict[str, Any] = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(),
        "counts": {
            "personas": len(personas),
            "worldbook_entries": len(entries),
            "sessions": len(sessions),
            "messages": len(messages),
            "memories": len(memories),
            "feedbacks": db.query(Feedback).count() if include_feedback else 0,
            "import_batches": db.query(ImportBatch).count() if include_import_batches else 0,
        },
        "settings": {
            key: ("" if key in ALWAYS_SECRET_KEYS else value)
            for key, value in (get_runtime_config(db) or {}).items()
        },
        "personas": persona_items,
    }
    # 掩码：导出文件里绝不出现明文密钥
    for key in ALWAYS_SECRET_KEYS:
        raw = str((get_runtime_config(db) or {}).get(key) or "")
        payload["settings"][key] = mask_secret(raw) if raw else ""
    payload["settings"]["llm_api_key_set"] = bool(
        str((get_runtime_config(db) or {}).get("llm_api_key") or "").strip()
    )

    if include_feedback:
        payload["feedbacks"] = [
            export_feedback(row) for row in db.query(Feedback).order_by(Feedback.id.asc()).all()
        ]
    if include_import_batches:
        payload["import_batches"] = [
            export_import_batch(row) for row in db.query(ImportBatch).order_by(ImportBatch.id.asc()).all()
        ]
    return payload


@router.get("/export")
def export_backup(
    include_import_batches: bool = Query(default=False, description="是否含导入批次（体积较大）"),
    include_feedback: bool = Query(default=True, description="是否含点赞/改写样本"),
    download: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    payload = build_backup(db, include_import_batches=include_import_batches, include_feedback=include_feedback)
    filename = f"cyber-girlfriend-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"}
    if not download:
        headers.pop("Content-Disposition", None)
    return JSONResponse(content=payload, headers=headers)


# --------------------------------------------------------------------------
# 导入
# --------------------------------------------------------------------------
def _next_free_id(db: Session, model: Any, old_id: Any, used: set) -> Optional[int]:
    """旧 id 可用则沿用；被占用则交给自增（返回 None）。"""
    if old_id is None:
        return None
    try:
        value = int(old_id)
    except (TypeError, ValueError):
        return None
    if value in used:
        return None
    return value if db.get(model, value) is None else None


def import_backup(
    db: Session,
    payload: Dict[str, Any],
    strategy: str = "merge_by_id",
    dry_run: bool = False,
    import_settings: bool = True,
    import_api_key: bool = False,
) -> Dict[str, Any]:
    """把备份 payload 合并进当前库，返回统计报告。"""
    created: Dict[str, int] = {}
    skipped: Dict[str, int] = {}
    remapped: Dict[str, int] = {}
    warnings: List[str] = []

    def bump(bucket: Dict[str, int], key: str, delta: int = 1) -> None:
        bucket[key] = bucket.get(key, 0) + delta

    # ---- 设置 ----
    settings_in = payload.get("settings")
    if import_settings and isinstance(settings_in, dict):
        updates: Dict[str, Any] = {}
        for key in IMPORTABLE_SETTINGS:
            if key in settings_in and settings_in[key] is not None:
                updates[key] = settings_in[key]
        if not import_api_key and "llm_api_key" in settings_in:
            warnings.append("llm_api_key 未导入（默认忽略密钥，避免把掩码串写回数据库）")
        if import_api_key:
            raw_key = as_str(settings_in.get("llm_api_key"))
            if raw_key and "*" not in raw_key:
                updates["llm_api_key"] = raw_key
            elif raw_key:
                warnings.append("llm_api_key 为掩码串，已跳过（无法从掩码还原明文密钥）")
        if updates:
            if not dry_run:
                set_runtime_config(db, updates)
            created["settings"] = len(updates)

    persona_map: Dict[int, int] = {}
    session_map: Dict[int, int] = {}
    message_map: Dict[int, int] = {}
    used_persona_ids: set = set()
    used_entry_ids: set = set()
    used_session_ids: set = set()
    used_message_ids: set = set()
    used_memory_ids: set = set()

    for item in payload.get("personas") or []:
        if not isinstance(item, dict):
            continue
        old_id = as_int(item.get("id"), 0)
        name = as_str(item.get("name")).strip() or "未命名角色"

        existing: Optional[Persona] = None
        if strategy in ("merge_by_id", "skip_duplicates") and old_id:
            existing = db.get(Persona, old_id)
        if existing is None and strategy in ("merge_by_name", "skip_duplicates"):
            existing = db.query(Persona).filter(Persona.name == name).first()

        if existing is not None and strategy == "skip_duplicates":
            persona_map[old_id] = existing.id
            bump(skipped, "personas")
        else:
            target_id = None
            if existing is None:
                target_id = _next_free_id(db, Persona, old_id, used_persona_ids)
                used_persona_ids.add(target_id if target_id is not None else old_id)
                existing = Persona(id=target_id) if target_id is not None else Persona()
                _fill_persona(existing, item)
                db.add(existing)
                if not dry_run:
                    db.flush()
                bump(created, "personas")
            else:
                _fill_persona(existing, item)
                bump(created, "personas_updated")
            persona_map[old_id] = existing.id if existing.id is not None else old_id

        persona_id = persona_map.get(old_id) or existing.id
        if old_id and persona_id and int(persona_id) != int(old_id):
            remapped["personas"] = remapped.get("personas", 0) + 1

        # ---- 世界书 ----
        for entry_item in item.get("worldbook") or []:
            if not isinstance(entry_item, dict) or not as_str(entry_item.get("content")).strip():
                continue
            existing_entry = None
            old_entry_id = as_int(entry_item.get("id"), 0)
            if strategy != "skip_duplicates" and old_entry_id:
                existing_entry = db.get(WorldBookEntry, old_entry_id)
            if existing_entry is None:
                keys = entry_item.get("keys") or []
                existing_entry = (
                    db.query(WorldBookEntry)
                    .filter(
                        WorldBookEntry.persona_id == persona_id,
                        WorldBookEntry.content == as_str(entry_item.get("content")),
                    )
                    .first()
                )
            if existing_entry is not None:
                bump(skipped, "worldbook_entries")
                continue

            entry_id = _next_free_id(db, WorldBookEntry, old_entry_id, used_entry_ids)
            used_entry_ids.add(entry_id if entry_id is not None else old_entry_id)
            entry = WorldBookEntry(id=entry_id) if entry_id is not None else WorldBookEntry()
            _fill_entry(entry, entry_item, persona_id)
            db.add(entry)
            if not dry_run:
                db.flush()
            bump(created, "worldbook_entries")

        # ---- 记忆 ----
        for memory_item in item.get("memories") or []:
            if not isinstance(memory_item, dict) or not as_str(memory_item.get("content")).strip():
                continue
            old_memory_id = as_int(memory_item.get("id"), 0)
            found = db.get(Memory, old_memory_id) if old_memory_id else None
            if found is not None:
                bump(skipped, "memories")
                continue
            memory_id = _next_free_id(db, Memory, old_memory_id, used_memory_ids)
            used_memory_ids.add(memory_id if memory_id is not None else old_memory_id)
            memory = Memory(id=memory_id) if memory_id is not None else Memory()
            memory.persona_id = persona_id
            session_ref = memory_item.get("session_id")
            memory.session_id = session_map.get(as_int(session_ref, -1)) if session_ref is not None else None
            memory.content = as_str(memory_item.get("content"))
            memory.kind = as_str(memory_item.get("kind"), "fact") or "fact"
            memory.importance = as_float(memory_item.get("importance"), 0.5)
            memory.source = as_str(memory_item.get("source"), "backup") or "backup"
            memory.created_at = dt_from_iso(memory_item.get("created_at")) or datetime.now()
            memory.last_access_at = dt_from_iso(memory_item.get("last_access_at"))
            memory.access_count = as_int(memory_item.get("access_count"), 0)
            db.add(memory)
            if not dry_run:
                db.flush()
            bump(created, "memories")

        # ---- 会话 + 消息 ----
        for session_item in item.get("sessions") or []:
            if not isinstance(session_item, dict):
                continue
            old_session_id = as_int(session_item.get("id"), 0)
            found = db.get(ChatSession, old_session_id) if old_session_id else None
            if found is not None:
                session_map[old_session_id] = found.id
                bump(skipped, "sessions")
            else:
                session_id = _next_free_id(db, ChatSession, old_session_id, used_session_ids)
                used_session_ids.add(session_id if session_id is not None else old_session_id)
                session = ChatSession(id=session_id) if session_id is not None else ChatSession()
                session.persona_id = persona_id
                session.title = as_str(session_item.get("title"), "新的对话") or "新的对话"
                session.mood = as_int(session_item.get("mood"), 65)
                session.affection = as_int(session_item.get("affection"), 50)
                session.summary = as_str(session_item.get("summary"))
                session.created_at = dt_from_iso(session_item.get("created_at")) or datetime.now()
                session.updated_at = dt_from_iso(session_item.get("updated_at")) or session.created_at
                db.add(session)
                if not dry_run:
                    db.flush()
                session_map[old_session_id] = session.id if session.id is not None else old_session_id
                if old_session_id and session_map[old_session_id] != old_session_id:
                    remapped["sessions"] = remapped.get("sessions", 0) + 1
                bump(created, "sessions")

            target_session_id = session_map.get(old_session_id)
            for message_item in session_item.get("messages") or []:
                if not isinstance(message_item, dict):
                    continue
                old_message_id = as_int(message_item.get("id"), 0)
                if old_message_id and db.get(Message, old_message_id) is not None:
                    message_map[old_message_id] = old_message_id
                    bump(skipped, "messages")
                    continue
                message_id = _next_free_id(db, Message, old_message_id, used_message_ids)
                used_message_ids.add(message_id if message_id is not None else old_message_id)
                message = Message(id=message_id) if message_id is not None else Message()
                message.session_id = target_session_id
                message.role = as_str(message_item.get("role"), "assistant") or "assistant"
                message.content = as_str(message_item.get("content"))
                message.created_at = dt_from_iso(message_item.get("created_at")) or datetime.now()
                message.feedback = as_int(message_item.get("feedback"), 0)
                message.rewritten = as_bool(message_item.get("rewritten"), False)
                db.add(message)
                if not dry_run:
                    db.flush()
                message_map[old_message_id] = message.id if message.id is not None else old_message_id
                if old_message_id and message_map[old_message_id] != old_message_id:
                    remapped["messages"] = remapped.get("messages", 0) + 1
                bump(created, "messages")

    # ---- 反馈样本 ----
    for item in payload.get("feedbacks") or []:
        if not isinstance(item, dict):
            continue
        old_id = as_int(item.get("id"), 0)
        if old_id and db.get(Feedback, old_id) is not None:
            bump(skipped, "feedbacks")
            continue
        row = Feedback(id=old_id or None) if old_id else Feedback()
        row.persona_id = persona_map.get(as_int(item.get("persona_id"), -1))
        row.session_id = session_map.get(as_int(item.get("session_id"), -1))
        row.message_id = message_map.get(as_int(item.get("message_id"), -1))
        row.action = as_str(item.get("action"), "like") or "like"
        row.original = as_str(item.get("original"))
        row.revised = as_str(item.get("revised"))
        row.created_at = dt_from_iso(item.get("created_at")) or datetime.now()
        db.add(row)
        bump(created, "feedbacks")

    if dry_run:
        db.rollback()
    else:
        db.commit()

    for table in ("personas", "sessions", "messages"):
        if remapped.get(table):
            warnings.append(f"{table} 有 {remapped[table]} 条记录因 id 冲突被重新编号（外键已同步重映射）")

    return {
        "ok": True,
        "strategy": strategy,
        "dry_run": bool(dry_run),
        "created": created,
        "skipped": skipped,
        "remapped": remapped,
        "warnings": warnings,
        "counts": payload.get("counts") or {},
    }


def _fill_persona(persona: Persona, item: Dict[str, Any]) -> None:
    persona.name = (as_str(item.get("name")).strip() or "未命名角色")[:64]
    persona.avatar_emoji = as_str(item.get("avatar_emoji"), "🌸") or "🌸"
    persona.relation = as_str(item.get("relation"), "女友") or "女友"
    persona.nickname_for_user = as_str(item.get("nickname_for_user"), "你") or "你"
    persona.greeting = as_str(item.get("greeting"))
    persona.source = as_str(item.get("source"), "backup") or "backup"
    persona.creator_notes = as_str(item.get("creator_notes"))
    persona.character_version = as_str(item.get("character_version"))[:64]
    persona.card_spec = as_str(item.get("card_spec"))[:32]
    persona.set_card(item.get("persona_card") or {})
    persona.set_sliders(item.get("sliders") or {})
    persona.set_tag_list(item.get("tags") or [])
    persona.set_extensions(item.get("extensions") or {})
    persona.created_at = dt_from_iso(item.get("created_at")) or datetime.now()


def _fill_entry(entry: WorldBookEntry, item: Dict[str, Any], persona_id: int) -> None:
    entry.persona_id = persona_id
    entry.content = as_str(item.get("content"))
    entry.enabled = as_bool(item.get("enabled"), True)
    entry.constant = as_bool(item.get("constant"), False)
    entry.case_sensitive = as_bool(item.get("case_sensitive"), False)
    entry.priority = as_int(item.get("priority"), 100)
    entry.position = as_str(item.get("position"), "before_char") or "before_char"
    entry.depth = as_int(item.get("depth"), 4)
    entry.token_budget = as_int(item.get("token_budget"), 0)
    entry.comment = as_str(item.get("comment"))[:128]
    entry.source = as_str(item.get("source"), "backup") or "backup"
    entry.set_key_list(item.get("keys") or [])
    entry.created_at = dt_from_iso(item.get("created_at")) or datetime.now()


@router.post("/import")
async def import_backup_api(
    file: UploadFile = File(...),
    strategy: str = Query(default="merge_by_id", description="merge_by_id | merge_by_name | skip_duplicates"),
    dry_run: bool = Query(default=False, description="只试算不落库"),
    import_api_key: bool = Query(default=False, description="是否导入 API Key（默认忽略）"),
    db: Session = Depends(get_db),
) -> Any:
    strategy_key = (strategy or "merge_by_id").strip().lower()
    if strategy_key not in VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"strategy 仅支持 {'/'.join(VALID_STRATEGIES)}")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="备份文件过大（>64MB）")

    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"备份文件不是合法的 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="备份文件结构无效（顶层必须是对象）")

    fmt = as_str(payload.get("format"))
    if fmt and fmt != FORMAT_NAME:
        raise HTTPException(status_code=400, detail=f"不是本项目的备份文件（format={fmt}）")
    if not fmt and not isinstance(payload.get("personas"), list):
        raise HTTPException(status_code=400, detail="备份文件缺少 personas 字段，无法导入")

    report = import_backup(
        db,
        payload,
        strategy=strategy_key,
        dry_run=bool(dry_run),
        import_settings=True,
        import_api_key=bool(import_api_key),
    )
    return report


__all__ = ["build_backup", "export_backup", "import_backup", "router"]
