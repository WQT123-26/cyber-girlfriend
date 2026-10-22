"""聊天记录导入 API。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_runtime_config
from app.db.base import get_db
from app.models.models import ImportBatch
from app.schemas.schemas import ImportBatchOut
from app.services.importer.desensitize import config_from_runtime
from app.services.importer.parser import parse_bytes

router = APIRouter(prefix="/import", tags=["import"])

MAX_UPLOAD_BYTES = 24 * 1024 * 1024  # 24MB，避免误传超大文件


def batch_to_dict(batch: ImportBatch) -> Dict[str, Any]:
    messages = batch.message_list()
    stats = batch.stats_dict()
    return {
        "id": batch.id,
        "filename": batch.filename,
        "fmt": batch.fmt,
        "message_count": batch.message_count,
        "speakers": batch.speaker_list(),
        "preview": batch.preview_list() or messages[-10:],
        "messages": messages,
        "created_at": batch.created_at,
        # 脱敏：开关状态 + 各类命中统计（前端预览展示）
        "desensitize_enabled": bool(batch.desensitize_enabled),
        "desensitize": stats,
    }


@router.post("/upload", response_model=ImportBatchOut)
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
    filename = file.filename or "upload.txt"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大（上限 24MB），请先裁剪聊天记录")

    desensitize_cfg = config_from_runtime(get_runtime_config(db))
    try:
        parsed = parse_bytes(filename, raw, desensitize_config=desensitize_cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # 解析失败统一转成 400，避免 500
        raise HTTPException(status_code=400, detail=f"解析失败：{exc}")

    messages = parsed.get("messages") or []
    if not messages:
        raise HTTPException(
            status_code=400,
            detail="未能从文件中解析出任何消息，请检查格式（支持微信/QQ 导出的 txt、Telegram 导出的 json、通用 csv）",
        )

    batch = ImportBatch(
        filename=filename,
        fmt=parsed.get("fmt") or "unknown",
        message_count=len(messages),
    )
    batch.set_speaker_list(parsed.get("speakers") or [])
    batch.set_message_list(messages)
    batch.set_preview_list(messages[-10:])
    # 脱敏结果落库，供预览页展示「开关状态 + 各类命中次数」
    stats = parsed.get("desensitize") or {}
    batch.desensitize_enabled = bool(stats.get("enabled", True))
    batch.set_stats_dict(stats)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch_to_dict(batch)


@router.get("/batches", response_model=List[ImportBatchOut])
def list_batches(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(50).all()
    return [batch_to_dict(item) for item in rows]


@router.get("/batches/{batch_id}", response_model=ImportBatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return batch_to_dict(batch)


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    db.delete(batch)
    db.commit()
    return {"ok": True, "deleted_batch_id": batch_id}


__all__ = ["router", "batch_to_dict"]
