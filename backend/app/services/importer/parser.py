"""聊天记录解析器。

支持格式（自动识别，无需用户选择）：
    * 微信 PC 端导出的 txt      -> ``wechat_txt``
    * QQ 消息管理器导出的 txt   -> ``qq_txt``
    * Telegram Desktop 导出的 json -> ``telegram_json``
    * 通用 json（数组 / {"messages": [...]}） -> ``generic_json``
    * 通用 csv（含表头列名识别） -> ``csv``
    * 上面都不匹配时的 ``昵称: 内容`` 文本 -> ``plain_txt``

统一输出结构::

    {
      "fmt": "wechat_txt",
      "messages": [{"speaker": "小明", "content": "你好", "timestamp": "..."}],
      "speakers": [{"name": "小明", "count": 12}],
      "message_count": 20,
      "raw_message_count": 22,          # 脱敏丢弃黑名单消息前的条数
      "preview": [ ...最后 10 条... ],
      "desensitize": {                  # 脱敏开关与各类命中统计（前端预览展示用）
        "enabled": True,
        "counts": {"phone": 1, "email": 0, ...},
        "counts_labeled": {"手机号": 1, ...},
        "total_masked": 1,
        "dropped_messages": 2,
        "dropped_keywords": ["广告"]
      }
    }

脱敏（``app.services.importer.desensitize``）默认开启，作用于最终消息列表：
订单/联系方式等敏感内容被替换为占位符，命中黑名单关键词的消息整条丢弃。
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List, Optional

from app.services.importer.desensitize import (
    DesensitizeConfig,
    build_config,
    desensitize_messages,
    empty_stats,
)

SUPPORTED_EXTS = (".txt", ".json", ".csv")
MAX_MESSAGES = 20000

_TS = r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?"
_RE_HEAD = re.compile(rf"^(?P<ts>{_TS})\s+(?P<name>.+?)\s*$")
_RE_TAIL = re.compile(rf"^(?P<name>.+?)\s+(?P<ts>{_TS})\s*$")
_RE_NAME_TAIL_ID = re.compile(r"[（(]\s*\d+\s*[)）]\s*$")
_RE_LOOSE = re.compile(r"^(?P<name>[^:：]{1,24})[:：]\s*(?P<content>.+)$")
_RE_SEP = re.compile(r"^\s*(=+|-+|\*+)\s*(消息记录|聊天记录|消息列表)?\s*(=+|-+|\*+)?\s*$")

_SPEAKER_KEYS = [
    "speaker", "sender", "from", "name", "user", "author", "nickname", "role",
    "发送者", "发送人", "昵称", "用户名", "说话人", "用户",
]
_CONTENT_KEYS = [
    "content", "text", "message", "body", "msg", "content_text",
    "内容", "消息", "消息内容", "文本", "聊天内容",
]
_TIME_KEYS = ["timestamp", "time", "date", "datetime", "created_at", "时间", "时间戳", "发送时间"]


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _decode(raw: bytes) -> str:
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "ignore")


def _clean_name(name: str) -> str:
    name = str(name or "").strip()
    name = _RE_NAME_TAIL_ID.sub("", name).strip()
    name = name.strip(":： \t")
    return name or "未知"


def _clean_content(content: Any) -> str:
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        content = "".join(parts)
    text = str(content or "").replace("\u200b", "").replace("\r\n", "\n")
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join([line for line in lines if line]).strip()


def _norm_ts(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _summarize(messages: List[Dict[str, str]], fmt: str) -> Dict[str, Any]:
    """按消息列表重算 speakers / preview / message_count。"""
    counter: Dict[str, int] = {}
    for item in messages:
        counter[item["speaker"]] = counter.get(item["speaker"], 0) + 1
    speakers = [{"name": name, "count": count} for name, count in sorted(counter.items(), key=lambda kv: -kv[1])]

    return {
        "fmt": fmt,
        "messages": messages,
        "speakers": speakers,
        "message_count": len(messages),
        "preview": messages[-10:],
    }


def _finalize(messages: List[Dict[str, str]], fmt: str) -> Dict[str, Any]:
    cleaned: List[Dict[str, str]] = []
    for item in messages:
        speaker = _clean_name(item.get("speaker"))
        content = _clean_content(item.get("content"))
        if not content:
            continue
        cleaned.append({"speaker": speaker, "content": content, "timestamp": _norm_ts(item.get("timestamp"))})
        if len(cleaned) >= MAX_MESSAGES:
            break

    return _summarize(cleaned, fmt)


def _apply_desensitize(result: Dict[str, Any], config: Optional[DesensitizeConfig]) -> Dict[str, Any]:
    """对解析结果统一执行脱敏，并附带统计信息。"""
    cfg = config if isinstance(config, DesensitizeConfig) else build_config()
    raw_messages = list(result.get("messages") or [])
    masked, stats = desensitize_messages(raw_messages, cfg)

    result["raw_message_count"] = len(raw_messages)
    result["desensitize"] = stats
    if len(masked) != len(raw_messages) or stats.get("total_masked"):
        summary = _summarize(masked, str(result.get("fmt") or "unknown"))
        result["messages"] = summary["messages"]
        result["speakers"] = summary["speakers"]
        result["message_count"] = summary["message_count"]
        result["preview"] = summary["preview"]
    return result


# --------------------------------------------------------------------------
# TXT
# --------------------------------------------------------------------------
def _parse_txt(text: str) -> Dict[str, Any]:
    messages: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    head_hits = 0
    tail_hits = 0
    tail_id_hits = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if _RE_SEP.match(stripped):
            continue

        matched = None
        head = _RE_HEAD.match(stripped)
        tail = _RE_TAIL.match(stripped) if not head else None
        if head:
            matched = ("head", head.group("ts"), head.group("name"))
        elif tail:
            matched = ("tail", tail.group("ts"), tail.group("name"))

        if matched:
            if matched[0] == "head":
                head_hits += 1
            else:
                tail_hits += 1
                if _RE_NAME_TAIL_ID.search(matched[2]):
                    tail_id_hits += 1
            current = {"speaker": matched[2], "content": "", "timestamp": matched[1]}
            messages.append(current)
            continue

        if current is not None:
            current["content"] = f"{current['content']}\n{stripped}" if current["content"] else stripped
            continue

        # 文件开头没有时间戳，尝试 "昵称: 内容"
        loose = _RE_LOOSE.match(stripped)
        if loose:
            messages.append({"speaker": loose.group("name"), "content": loose.group("content"), "timestamp": ""})
            continue
        messages.append({"speaker": "对方", "content": stripped, "timestamp": ""})

    if head_hits == 0 and tail_hits == 0:
        # 完全没识别出时间戳：重新按 "昵称: 内容" 解析
        fallback: List[Dict[str, str]] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped or _RE_SEP.match(stripped):
                continue
            loose = _RE_LOOSE.match(stripped)
            if loose:
                fallback.append({"speaker": loose.group("name"), "content": loose.group("content"), "timestamp": ""})
            else:
                fallback.append({"speaker": "对方", "content": stripped, "timestamp": ""})
        return _finalize(fallback, "plain_txt")

    if tail_hits > head_hits and tail_id_hits > 0:
        fmt = "qq_txt"
    elif tail_hits > head_hits:
        fmt = "qq_txt"
    else:
        fmt = "wechat_txt"
    return _finalize(messages, fmt)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------
def _pick(obj: Dict[str, Any], keys: List[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
            return lowered[key.lower()]
    return None


def _json_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("messages", "data", "items", "records", "list", "chats", "log"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _parse_json(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return _parse_txt(text)

    items = _json_items(data)
    if not items:
        return _finalize([], "generic_json")

    is_telegram = isinstance(data, dict) and any(
        str(k).lower() in {"messages", "chats"} for k in data.keys()
    ) and all(("from" in item or "from_id" in item) for item in items[:5])

    messages: List[Dict[str, str]] = []
    for item in items:
        if str(item.get("type") or "message") not in ("message", ""):
            continue
        speaker = _pick(item, ["from", "speaker", "sender", "name", "user", "author", "昵称", "发送者"])
        if speaker is None:
            speaker = str(item.get("from_id") or "对方")
        content = _pick(item, ["text", "content", "message", "body", "消息", "内容"])
        if content is None:
            continue
        timestamp = _pick(item, ["date", "timestamp", "time", "datetime", "时间"])
        messages.append({"speaker": str(speaker), "content": content, "timestamp": _norm_ts(timestamp)})

    return _finalize(messages, "telegram_json" if is_telegram else "generic_json")


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def _parse_csv(text: str) -> Dict[str, Any]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(str(cell).strip() for cell in row)]
    if not rows:
        return _finalize([], "csv")

    header = [str(cell).strip() for cell in rows[0]]
    lowered = [cell.lower() for cell in header]

    def find_index(keys: List[str]) -> int:
        for key in keys:
            for index, cell in enumerate(lowered):
                if cell == key.lower():
                    return index
        for key in keys:
            for index, cell in enumerate(lowered):
                if key.lower() in cell:
                    return index
        return -1

    speaker_idx = find_index(_SPEAKER_KEYS)
    content_idx = find_index(_CONTENT_KEYS)
    time_idx = find_index(_TIME_KEYS)

    has_header = speaker_idx >= 0 and content_idx >= 0
    body = rows[1:] if has_header else rows
    if not has_header:
        if len(header) >= 2:
            time_idx, speaker_idx, content_idx = (-1, 0, 1)
        else:
            speaker_idx, content_idx = (-1, 0)

    messages: List[Dict[str, str]] = []
    for row in body:
        def cell(index: int) -> str:
            return row[index].strip() if 0 <= index < len(row) else ""

        speaker = cell(speaker_idx) if speaker_idx >= 0 else "对方"
        content = cell(content_idx)
        if not content:
            continue
        messages.append({"speaker": speaker, "content": content, "timestamp": cell(time_idx)})

    return _finalize(messages, "csv")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def parse_bytes(
    filename: str,
    raw: Any,
    desensitize_config: Optional[DesensitizeConfig] = None,
) -> Dict[str, Any]:
    """按扩展名与内容自动识别并解析。

    ``desensitize_config`` 为空时使用默认配置（默认开启脱敏）；
    解析结果中始终包含 ``desensitize`` 统计字段。
    """
    name = str(filename or "").lower()
    text = _decode(raw if isinstance(raw, bytes) else str(raw or "").encode("utf-8"))

    if name.endswith(".json"):
        result = _parse_json(text)
    elif name.endswith(".csv"):
        result = _parse_csv(text)
    elif name.endswith(".txt"):
        result = _parse_txt(text)
    else:
        # 未知扩展名：按内容猜
        stripped = text.lstrip()
        first_line = text.splitlines()[0] if text.strip() else ""
        if stripped.startswith("{") or stripped.startswith("["):
            result = _parse_json(text)
        elif "\t" in first_line or first_line.count(",") >= 2:
            result = _parse_csv(text)
        else:
            result = _parse_txt(text)

    result["filename"] = str(filename or "")
    result = _apply_desensitize(result, desensitize_config)
    return result


# 便捷别名
detect_and_parse = parse_bytes

__all__ = [
    "SUPPORTED_EXTS",
    "MAX_MESSAGES",
    "detect_and_parse",
    "empty_stats",
    "parse_bytes",
]
