"""SillyTavern 角色卡导入 / 导出 API。

路径（挂载后前缀为 ``/api``）：
    POST /cards/import                  上传 .json / .png 角色卡 → 建 Persona（+世界书）
    POST /cards/parse                   同上但只解析不落库（前端预览用）
    GET  /personas/{id}/card.json       导出角色卡 JSON（spec=v1|v2|v3）
    GET  /personas/{id}/card.png        导出内嵌角色卡的 PNG（标准库手写 PNG）

解析与生成细节见 ``app.services.card.st_card``；导入时的脱敏见
``app.services.importer.desensitize``。
"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_runtime_config
from app.db.base import get_db
from app.models.models import Persona, WorldBookEntry
from app.schemas.schemas import CardImportOut, CardImportSummary
from app.services.card.st_card import (
    CardParseError,
    build_card_png,
    card_to_persona,
    parse_card_payload,
    persona_to_card,
)
from app.services.importer.desensitize import config_from_runtime, desensitize_fields
from app.services.lore.matcher import load_entries

router = APIRouter(tags=["cards"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 单文件 8MB 上限
# 需要脱敏的文本字段（name 保留原样，避免人格名被替换成占位符）
CARD_TEXT_FIELDS: List[str] = [
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "system_prompt",
    "post_history_instructions",
    "alternate_greetings",
    "character_book",
]
VALID_SPECS = ("v1", "v2", "v3")


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _merge_stats(target: Dict[str, Any], part: Dict[str, Any]) -> None:
    counts = target.setdefault("counts", {})
    for key, value in (part.get("counts") or {}).items():
        counts[key] = int(counts.get(key, 0)) + int(value or 0)
    target["dropped_messages"] = int(target.get("dropped_messages", 0)) + int(part.get("dropped_messages") or 0)
    keywords = target.setdefault("dropped_keywords", [])
    for keyword in part.get("dropped_keywords") or []:
        if keyword not in keywords:
            keywords.append(keyword)
    target["total_masked"] = int(sum(int(v or 0) for v in counts.values()))


def _finalize_stats(stats: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
    from app.services.importer.desensitize import CATEGORY_LABELS

    stats["enabled"] = bool(enabled)
    stats["counts"] = {key: int(value or 0) for key, value in (stats.get("counts") or {}).items()}
    stats["counts_labeled"] = {CATEGORY_LABELS.get(key, key): value for key, value in stats["counts"].items()}
    stats["total_masked"] = int(sum(stats["counts"].values()))
    return stats


def apply_desensitize(parsed: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """对解析出的角色卡文本字段做脱敏，就地改写 ``parsed['data']`` / ``extra``。

    返回统计字典（含各类命中次数与开关状态），供前端预览。
    """
    cfg = get_runtime_config(db) if db is not None else {}
    config = config_from_runtime(cfg)
    stats: Dict[str, Any] = {"counts": {}, "dropped_messages": 0, "dropped_keywords": []}

    data = parsed.get("data")
    if isinstance(data, dict):
        cleaned, part = desensitize_fields(data, CARD_TEXT_FIELDS, config)
        parsed["data"] = cleaned
        _merge_stats(stats, part)

    extra = parsed.get("extra")
    if isinstance(extra, dict) and extra:
        cleaned_extra, part = desensitize_fields(extra, list(extra.keys()), config)
        parsed["extra"] = cleaned_extra
        _merge_stats(stats, part)

    if config.blacklist:
        stats["blacklist"] = list(config.blacklist)
    return _finalize_stats(stats, config.enabled)


def build_summary(parsed: Dict[str, Any], stats: Dict[str, Any], worldbook_saved: int = 0) -> Dict[str, Any]:
    data = parsed.get("data") or {}
    dialogues = ((data.get("mes_example") or "") and len(card_to_persona(parsed)["persona_card"]["sample_dialogues"])) or 0
    return {
        "source_format": "png" if parsed.get("keyword") else "json",
        "spec": parsed.get("spec") or "",
        "spec_version": parsed.get("spec_version") or "",
        "card_format": parsed.get("format") or "",
        "png_keyword": parsed.get("keyword") or "",
        "fields_hit": list(parsed.get("fields_hit") or []),
        "fields_missing": list(parsed.get("fields_missing") or []),
        "greeting_length": len(data.get("first_mes") or ""),
        "sample_dialogue_count": int(dialogues),
        "alternate_greeting_count": len(data.get("alternate_greetings") or []),
        "worldbook_entry_count": len(card_to_persona(parsed)["worldbook"]),
        "worldbook_saved": int(worldbook_saved),
        "warnings": list(parsed.get("warnings") or []),
        "desensitize_enabled": bool(stats.get("enabled", True)),
        "desensitize": stats,
    }


async def read_upload(file: UploadFile) -> bytes:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件过大（>{MAX_UPLOAD_BYTES // 1024 // 1024}MB）")
    return payload


def parse_upload(payload: bytes, filename: str, db: Session) -> Dict[str, Any]:
    from app.services.card.st_card import normalize_card

    try:
        parsed = parse_card_payload(payload, filename=filename)
    except CardParseError as exc:
        raise HTTPException(status_code=400, detail=f"角色卡解析失败：{exc}") from exc
    except Exception as exc:  # 兜底：任何异常都转成可读 400
        raise HTTPException(status_code=400, detail=f"角色卡解析失败：{exc}") from exc
    if not isinstance(parsed, dict) or "data" not in parsed:
        parsed = normalize_card(parsed if isinstance(parsed, dict) else {})
    return parsed


def get_persona_or_404(db: Session, persona_id: int) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="人格不存在")
    return persona


def ascii_filename(name: str, suffix: str, fallback: str = "character") -> str:
    """构造 ASCII 安全的下载文件名（中文名回退到 fallback）。"""
    base = "".join(ch for ch in (name or "") if ch.isascii() and (ch.isalnum() or ch in "-_ ")).strip()
    return f"{base or fallback}{suffix}"


def content_disposition(filename: str, display_name: str) -> str:
    """同时给出 ASCII filename 与 RFC 5987 的 filename*（中文名可用）。"""
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(display_name)}"


# --------------------------------------------------------------------------
# 导入
# --------------------------------------------------------------------------
@router.post("/cards/import", response_model=CardImportOut)
async def import_card(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """上传酒馆角色卡（.json / .png），解析 → 脱敏 → 建人格（含世界书条目）。"""
    payload = await read_upload(file)
    parsed = parse_upload(payload, file.filename or "", db)
    stats = apply_desensitize(parsed, db)

    try:
        mapped = card_to_persona(parsed)
    except CardParseError as exc:
        raise HTTPException(status_code=400, detail=f"角色卡字段映射失败：{exc}") from exc

    warnings = list(mapped["summary"].get("warnings") or [])
    if stats.get("dropped_messages"):
        warnings.append(f"有 {stats['dropped_messages']} 处文本命中黑名单，已被丢弃")

    persona = Persona(
        name=mapped["name"] or "未命名角色",
        avatar_emoji=mapped["avatar_emoji"] or "💠",
        relation=mapped["relation"] or "女友",
        nickname_for_user=mapped["nickname_for_user"] or "你",
        greeting=mapped["greeting"] or "",
        source="card_import",
        creator_notes=mapped.get("creator_notes") or "",
        character_version=mapped.get("character_version") or "",
        card_spec=mapped.get("card_spec") or "",
    )
    persona.set_tag_list(mapped.get("tags") or [])
    persona.set_card(mapped["persona_card"] or {})
    persona.set_sliders(mapped.get("sliders") or {})
    persona.set_extensions(mapped.get("extensions") or {})
    db.add(persona)
    db.flush()

    saved_entries = 0
    for item in mapped.get("worldbook") or []:
        entry = WorldBookEntry(
            persona_id=persona.id,
            content=item.get("content") or "",
            enabled=bool(item.get("enabled", True)),
            constant=bool(item.get("constant", False)),
            case_sensitive=bool(item.get("case_sensitive", False)),
            priority=int(item.get("priority") or 100),
            position=item.get("position") or "before_char",
            depth=int(item.get("depth") or 4),
            token_budget=int(item.get("token_budget") or 0),
            comment=(item.get("comment") or "")[:128],
            source="card_import",
        )
        entry.set_key_list(item.get("keys") or [])
        db.add(entry)
        saved_entries += 1

    db.commit()
    db.refresh(persona)

    summary = build_summary(parsed, stats, worldbook_saved=saved_entries)
    summary["warnings"] = warnings

    from app.api.personas import persona_to_dict

    return {"ok": True, "persona": persona_to_dict(persona), "summary": summary}


@router.post("/cards/parse", response_model=CardImportSummary)
async def parse_card_only(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """只解析角色卡并返回摘要（不建人格），供前端导入前预览。"""
    payload = await read_upload(file)
    parsed = parse_upload(payload, file.filename or "", db)
    stats = apply_desensitize(parsed, db)
    mapped = card_to_persona(parsed)
    return build_summary(parsed, stats, worldbook_saved=len(mapped.get("worldbook") or []))


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------
@router.get("/personas/{persona_id}/card.json")
def export_card_json(
    persona_id: int,
    spec: str = Query(default="v2", description="v1 | v2 | v3"),
    download: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Response:
    persona = get_persona_or_404(db, persona_id)
    spec_key = (spec or "v2").strip().lower()
    if spec_key not in VALID_SPECS:
        raise HTTPException(status_code=400, detail=f"spec 仅支持 {'/'.join(VALID_SPECS)}")

    entries = load_entries(db, persona_id, enabled_only=False)
    card = persona_to_card(persona, entries, spec=spec_key)
    headers = {"Content-Disposition": content_disposition(ascii_filename(persona.name, ".json"), f"{persona.name}.json")}
    if not download:
        headers.pop("Content-Disposition", None)
    return JSONResponse(content=card, headers=headers)


@router.get("/personas/{persona_id}/card.png")
def export_card_png(
    persona_id: int,
    spec: str = Query(default="v2", description="v1 | v2 | v3"),
    size: int = Query(default=512, ge=64, le=1024, description="占位底图边长（像素）"),
    db: Session = Depends(get_db),
) -> Response:
    persona = get_persona_or_404(db, persona_id)
    spec_key = (spec or "v2").strip().lower()
    if spec_key not in VALID_SPECS:
        raise HTTPException(status_code=400, detail=f"spec 仅支持 {'/'.join(VALID_SPECS)}")

    entries = load_entries(db, persona_id, enabled_only=False)
    card = persona_to_card(persona, entries, spec=spec_key)
    try:
        png = build_card_png(card, size=int(size), spec=spec_key)
    except CardParseError as exc:
        raise HTTPException(status_code=400, detail=f"角色卡 PNG 生成失败：{exc}") from exc

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": content_disposition(
                ascii_filename(persona.name, ".png"), f"{persona.name}.png"
            )
        },
    )


__all__ = ["apply_desensitize", "build_summary", "router"]
