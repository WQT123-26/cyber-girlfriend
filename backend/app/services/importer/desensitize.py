"""聊天记录 / 角色卡导入的隐私脱敏。

设计目标
--------
* **零依赖**：只用 Python 标准库 ``re``（不引入任何 NLP / 识别库）。
* **可配置**：是否启用 → ``CG_DESENSITIZE_ENABLED`` / DB ``desensitize_enabled``；
  关键词黑名单 → ``desensitize_blacklist``（逗号 / 换行分隔，或 JSON 数组）。
* **可观测**：每次脱敏都返回各类命中次数统计，供前端预览展示。

覆盖的敏感类型
--------------
================  ==========================  ==================
类型              规则                         占位符
================  ==========================  ==================
手机号            中国大陆 ``1[3-9]\\d{9}``      ``<手机号>``
身份证            18 位（含校验位校验）        ``<身份证>``
邮箱              常规 email 形式              ``<邮箱>``
银行卡            13~19 位连续数字             ``<银行卡>``
URL               http(s):// 与 www. 开头     ``<链接>``
IPv4              四段 0~255                   ``<IP>``
QQ 号             5~11 位且带上下文线索        ``<QQ号>``
================  ==========================  ==================

黑名单
------
命中黑名单关键词的**整条消息会被丢弃**（不进入后续人格提取 / 入库），
参考同类开源项目「敏感词直接整句过滤」的做法，避免污染人格语料。

注意：``enabled=False`` 时脱敏与黑名单**同时关闭**（统计里会如实标注）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
PLACEHOLDERS: Dict[str, str] = {
    "phone": "<手机号>",
    "id_card": "<身份证>",
    "email": "<邮箱>",
    "bank_card": "<银行卡>",
    "url": "<链接>",
    "ipv4": "<IP>",
    "qq": "<QQ号>",
}

# 统计里展示用的中文名
CATEGORY_LABELS: Dict[str, str] = {
    "phone": "手机号",
    "id_card": "身份证",
    "email": "邮箱",
    "bank_card": "银行卡",
    "url": "链接",
    "ipv4": "IP",
    "qq": "QQ号",
    "blacklist": "黑名单命中",
}

# 应用顺序很重要：先长后短，避免占位符里的字符被后续规则二次处理
APPLY_ORDER: Tuple[str, ...] = ("url", "email", "id_card", "bank_card", "phone", "ipv4", "qq")

_RE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'，。、；：）)】\]}]+", re.IGNORECASE)
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+")
_RE_ID_CARD = re.compile(
    r"(?<![0-9A-Za-z])[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])"
)
# 末尾排除 X/x：18 位身份证被误判/校验失败时，不应把前 18 位数字当成银行卡
_RE_BANK_CARD = re.compile(r"(?<!\d)\d{13,19}(?![\dXx])")
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_RE_IPV4 = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"
)
# QQ 号：必须有上下文线索（QQ / 企鹅 / 扣扣 / qq群 等）才认为是 QQ 号，避免误伤普通数字
_RE_QQ = re.compile(
    r"(?i)((?:qq|q)\s*(?:号|号码)?|企鹅号|扣扣|qq\s*群|q\s*群)\s*[:：=＝是为]?\s*(\d{5,11})(?!\d)"
)

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CHARS = "10X98765432"


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
@dataclass
class DesensitizeConfig:
    """一次脱敏所采用的规则配置。"""

    enabled: bool = True
    blacklist: List[str] = field(default_factory=list)
    mask_types: Tuple[str, ...] = APPLY_ORDER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "blacklist": list(self.blacklist),
            "mask_types": list(self.mask_types),
            "placeholders": {key: PLACEHOLDERS[key] for key in self.mask_types},
        }


def parse_blacklist(raw: Any) -> List[str]:
    """把黑名单配置解析成去重后的关键词列表。

    支持三种写法：
        * JSON 数组字符串：``["a", "b"]``
        * 逗号 / 顿号 / 分号分隔：``a,b；c``
        * 换行分隔（多行文本）
    """
    if raw is None:
        return []
    items: List[str] = []
    if isinstance(raw, (list, tuple, set)):
        items = [str(item) for item in raw]
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                items = [str(item) for item in parsed]
            else:
                items = re.split(r"[,，;；\n\r]+", text)
        else:
            items = re.split(r"[,，;；\n\r]+", text)

    result: List[str] = []
    seen = set()
    for item in items:
        keyword = str(item or "").strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
    return result


def build_config(
    enabled: Optional[bool] = None,
    blacklist: Any = None,
    mask_types: Optional[Sequence[str]] = None,
) -> DesensitizeConfig:
    """构造脱敏配置（缺省值来自 ``app.core.config.settings``）。"""
    from app.core.config import settings

    return DesensitizeConfig(
        enabled=settings.desensitize_enabled if enabled is None else bool(enabled),
        blacklist=parse_blacklist(settings.desensitize_blacklist if blacklist is None else blacklist),
        mask_types=tuple(mask_types) if mask_types else APPLY_ORDER,
    )


def config_from_runtime(cfg: Optional[Dict[str, Any]] = None) -> DesensitizeConfig:
    """从 ``get_runtime_config(db)`` 的运行时配置字典构造脱敏配置。"""
    if not cfg:
        return build_config()
    enabled = cfg.get("desensitize_enabled")
    return build_config(
        enabled=None if enabled is None else bool(enabled),
        blacklist=cfg.get("desensitize_blacklist"),
    )


def empty_stats(config: Optional[DesensitizeConfig] = None) -> Dict[str, Any]:
    """空统计骨架（前端可直接渲染）。"""
    config = config or build_config()
    return {
        "enabled": bool(config.enabled),
        "blacklist": list(config.blacklist),
        "counts": {key: 0 for key in config.mask_types},
        "counts_labeled": {CATEGORY_LABELS.get(key, key): 0 for key in config.mask_types},
        "total_masked": 0,
        "dropped_messages": 0,
        "dropped_keywords": [],
    }


# --------------------------------------------------------------------------
# 规则
# --------------------------------------------------------------------------
def is_valid_id_card(value: str) -> bool:
    """18 位身份证校验位校验（不符合则不做脱敏，避免误伤普通数字串）。"""
    value = str(value or "").strip()
    if len(value) != 18:
        return False
    body = value[:17]
    if not body.isdigit():
        return False
    total = sum(int(ch) * weight for ch, weight in zip(body, _ID_WEIGHTS))
    return _ID_CHECK_CHARS[total % 11].lower() == value[17].lower()


def _mask_url(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["url"] += 1
        return PLACEHOLDERS["url"]

    return _RE_URL.sub(repl, text)


def _mask_email(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["email"] += 1
        return PLACEHOLDERS["email"]

    return _RE_EMAIL.sub(repl, text)


def _mask_id_card(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        value = match.group(0)
        if not is_valid_id_card(value):
            return value
        hits["id_card"] += 1
        return PLACEHOLDERS["id_card"]

    return _RE_ID_CARD.sub(repl, text)


def _mask_bank_card(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["bank_card"] += 1
        return PLACEHOLDERS["bank_card"]

    return _RE_BANK_CARD.sub(repl, text)


def _mask_phone(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["phone"] += 1
        return PLACEHOLDERS["phone"]

    return _RE_PHONE.sub(repl, text)


def _mask_ipv4(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["ipv4"] += 1
        return PLACEHOLDERS["ipv4"]

    return _RE_IPV4.sub(repl, text)


def _mask_qq(text: str, hits: Dict[str, int]) -> str:
    def repl(match: "re.Match[str]") -> str:
        hits["qq"] += 1
        return f"{match.group(1)}{PLACEHOLDERS['qq']}"

    return _RE_QQ.sub(repl, text)


_MASKERS = {
    "url": _mask_url,
    "email": _mask_email,
    "id_card": _mask_id_card,
    "bank_card": _mask_bank_card,
    "phone": _mask_phone,
    "ipv4": _mask_ipv4,
    "qq": _mask_qq,
}


def desensitize_text(text: Any, config: Optional[DesensitizeConfig] = None) -> Tuple[str, Dict[str, int]]:
    """对单段文本做脱敏，返回 ``(脱敏后文本, 各类命中次数)``。"""
    config = config or build_config()
    original = "" if text is None else str(text)
    hits: Dict[str, int] = {key: 0 for key in config.mask_types}
    if not config.enabled or not original:
        return original, hits

    result = original
    for key in APPLY_ORDER:
        if key not in config.mask_types:
            continue
        result = _MASKERS[key](result, hits)
    return result, hits


def match_blacklist(text: Any, config: Optional[DesensitizeConfig] = None) -> Optional[str]:
    """返回命中的第一个黑名单关键词（未命中返回 ``None``）。"""
    config = config or build_config()
    if not config.enabled or not config.blacklist:
        return None
    haystack = str(text or "")
    if not haystack:
        return None
    for keyword in config.blacklist:
        if keyword and keyword in haystack:
            return keyword
    return None


# --------------------------------------------------------------------------
# 批量入口
# --------------------------------------------------------------------------
def _merge_hits(total: Dict[str, int], part: Dict[str, int]) -> None:
    for key, value in (part or {}).items():
        if not value:
            continue
        total[key] = total.get(key, 0) + int(value)


def desensitize_messages(
    messages: Iterable[Dict[str, Any]],
    config: Optional[DesensitizeConfig] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """对消息列表做脱敏。

    * 命中黑名单的消息 **整条丢弃**
    * 其余消息按规则替换敏感内容

    返回 ``(处理后的消息列表, 统计字典)``。
    """
    config = config or build_config()
    stats = empty_stats(config)
    kept: List[Dict[str, Any]] = []
    dropped_keywords: List[str] = []

    for item in messages or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        speaker = item.get("speaker")

        if config.enabled:
            hit_keyword = match_blacklist(content, config) or match_blacklist(speaker, config)
            if hit_keyword:
                stats["dropped_messages"] += 1
                if hit_keyword not in dropped_keywords:
                    dropped_keywords.append(hit_keyword)
                continue

        masked_content, content_hits = desensitize_text(content, config)
        masked_speaker, speaker_hits = desensitize_text(speaker, config)
        _merge_hits(stats["counts"], content_hits)
        _merge_hits(stats["counts"], speaker_hits)

        row = dict(item)
        row["content"] = masked_content
        row["speaker"] = masked_speaker
        kept.append(row)

    stats["counts_labeled"] = {CATEGORY_LABELS.get(k, k): v for k, v in stats["counts"].items()}
    stats["total_masked"] = int(sum(stats["counts"].values()))
    stats["dropped_keywords"] = dropped_keywords
    return kept, stats


def desensitize_fields(
    data: Dict[str, Any],
    field_names: Sequence[str],
    config: Optional[DesensitizeConfig] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """对 dict 中指定字段做脱敏（用于角色卡导入）。

    值为列表时逐项处理；非字符串值原样保留。
    """
    config = config or build_config()
    stats = empty_stats(config)
    result = dict(data or {})
    dropped_keywords: List[str] = []

    for name in field_names:
        if name not in result:
            continue
        value = result[name]
        if isinstance(value, list):
            new_items: List[Any] = []
            for item in value:
                if isinstance(item, str):
                    if config.enabled:
                        hit_keyword = match_blacklist(item, config)
                        if hit_keyword:
                            stats["dropped_messages"] += 1
                            if hit_keyword not in dropped_keywords:
                                dropped_keywords.append(hit_keyword)
                            continue
                    masked, hits = desensitize_text(item, config)
                    _merge_hits(stats["counts"], hits)
                    new_items.append(masked)
                    continue
                if isinstance(item, dict):
                    # 列表里的字典（如角色卡 character_book.entries）继续下钻
                    nested, nested_stats = desensitize_fields(item, list(item.keys()), config)
                    new_items.append(nested)
                    _merge_hits(stats["counts"], nested_stats.get("counts") or {})
                    stats["dropped_messages"] += int(nested_stats.get("dropped_messages") or 0)
                    for keyword in nested_stats.get("dropped_keywords") or []:
                        if keyword not in dropped_keywords:
                            dropped_keywords.append(keyword)
                    continue
                new_items.append(item)
            result[name] = new_items
        elif isinstance(value, str):
            if config.enabled:
                hit_keyword = match_blacklist(value, config)
                if hit_keyword:
                    stats["dropped_messages"] += 1
                    if hit_keyword not in dropped_keywords:
                        dropped_keywords.append(hit_keyword)
                    result[name] = ""
                    continue
            masked, hits = desensitize_text(value, config)
            _merge_hits(stats["counts"], hits)
            result[name] = masked
        elif isinstance(value, dict):
            nested, nested_stats = desensitize_fields(value, list(value.keys()), config)
            result[name] = nested
            _merge_hits(stats["counts"], nested_stats.get("counts") or {})
            stats["dropped_messages"] += int(nested_stats.get("dropped_messages") or 0)
            for keyword in nested_stats.get("dropped_keywords") or []:
                if keyword not in dropped_keywords:
                    dropped_keywords.append(keyword)

    stats["counts_labeled"] = {CATEGORY_LABELS.get(k, k): v for k, v in stats["counts"].items()}
    stats["total_masked"] = int(sum(stats["counts"].values()))
    stats["dropped_keywords"] = dropped_keywords
    return result, stats


__all__ = [
    "APPLY_ORDER",
    "CATEGORY_LABELS",
    "DesensitizeConfig",
    "PLACEHOLDERS",
    "build_config",
    "config_from_runtime",
    "desensitize_fields",
    "desensitize_messages",
    "desensitize_text",
    "empty_stats",
    "is_valid_id_card",
    "match_blacklist",
    "parse_blacklist",
]
