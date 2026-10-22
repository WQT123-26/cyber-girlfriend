"""SillyTavern 角色卡（Character Card V1 / V2 / V3）解析与生成。

**零依赖**：只用 Python 标准库（``json`` / ``base64`` / ``struct`` / ``zlib`` / ``binascii``）。

能力
----
1. **解析**
   * 纯 JSON 角色卡：V2（``{"spec":"chara_card_v2","data":{...}}``）、
     V3（``chara_card_v3``）、V1（无 ``data`` 包裹的扁平结构）。
   * PNG 内嵌角色卡：读取 ``tEXt`` / ``zTXt`` / ``iTXt`` chunk，
     keyword 为 ``chara``（V2）或 ``ccv3``（V3），value 为 base64 后的 JSON。
2. **生成**
   * 生成标准 V2 / V3 / V1 JSON。
   * 生成内嵌角色卡的 PNG：底图用纯标准库现画的 512x512 渐变占位图
     （IHDR + IDAT(zlib 压缩的 filter 字节流) + IEND + tEXt）。
3. **字段映射**：角色卡 ⇄ 本项目 ``Persona`` 模型（见 ``card_to_persona`` /
   ``persona_to_card``），并支持 ``character_book`` → 世界书条目。

容错约定：所有解析失败统一抛 ``CardParseError``（``ValueError`` 子类），
消息为可直接展示给用户的中文描述，绝不向外抛未捕获异常。
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import struct
import zlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
V1_SPEC = ""
V2_SPEC = "chara_card_v2"
V2_SPEC_VERSION = "2.0"
V3_SPEC = "chara_card_v3"
V3_SPEC_VERSION = "3.0"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_KEYWORD_V2 = "chara"
TEXT_KEYWORD_V3 = "ccv3"
TEXT_KEYWORDS = (TEXT_KEYWORD_V3, TEXT_KEYWORD_V2)  # 读取优先级：V3 优先

# 角色卡标准字段（V2/V3）。V1 只使用其中前 6 个。
CARD_FIELDS: Tuple[str, ...] = (
    "name",
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
    "tags",
    "creator",
    "character_version",
    "extensions",
)

REQUIRED_ANY = ("name", "description", "first_mes")

_POSITION_ALIASES = {
    "before_char": "before_char",
    "before_char_defs": "before_char",
    "0": "before_char",
    "after_char": "after_char",
    "after_char_defs": "after_char",
    "1": "after_char",
    "at_depth": "at_depth",
    "2": "at_depth",
    "3": "at_depth",
    "4": "at_depth",
}


class CardParseError(ValueError):
    """角色卡无法解析（消息可直接展示给用户）。"""


# --------------------------------------------------------------------------
# PNG：chunk 级读写（纯标准库）
# --------------------------------------------------------------------------
def _iter_chunks(data: bytes) -> Iterable[Tuple[str, bytes]]:
    """遍历 PNG chunk，产出 ``(type, payload)``；CRC 校验失败直接跳过该 chunk。"""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 8:
        raise CardParseError("文件内容不是有效的 PNG（长度不足）")
    if bytes(data[:8]) != PNG_SIGNATURE:
        raise CardParseError("文件内容不是有效的 PNG（文件头签名不匹配）")

    offset = 8
    total = len(data)
    while offset + 8 <= total:
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        chunk_type = bytes(data[offset + 4 : offset + 8])
        start = offset + 8
        end = start + length
        if end + 4 > total:
            break
        payload = bytes(data[start:end])
        crc = struct.unpack(">I", data[end : end + 4])[0]
        try:
            expected = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        except Exception:  # pragma: no cover - binascii 不会失败，保险起见
            expected = crc
        if crc == expected:
            yield chunk_type.decode("latin-1"), payload
        offset = end + 4
        if chunk_type == b"IEND":
            break


def read_png_text_chunks(data: bytes) -> Dict[str, str]:
    """读取 PNG 中所有文本 chunk，返回 ``{keyword: text}``。

    支持 ``tEXt``（latin-1）、``zTXt``（zlib 压缩）、``iTXt``（UTF-8，可压缩）。
    """
    texts: Dict[str, str] = {}
    for chunk_type, payload in _iter_chunks(data):
        if chunk_type == "tEXt":
            keyword, _, text = bytes(payload).partition(b"\x00")
            if keyword:
                texts.setdefault(keyword.decode("latin-1", "ignore"), text.decode("latin-1", "ignore"))
        elif chunk_type == "zTXt":
            keyword, _, rest = bytes(payload).partition(b"\x00")
            if not keyword or len(rest) < 1:
                continue
            compressed = rest[1:]
            try:
                text = zlib.decompress(compressed).decode("latin-1", "ignore")
            except zlib.error:
                continue
            texts.setdefault(keyword.decode("latin-1", "ignore"), text)
        elif chunk_type == "iTXt":
            keyword, _, rest = bytes(payload).partition(b"\x00")
            if not keyword or len(rest) < 2:
                continue
            compressed_flag = rest[0]
            rest = rest[2:]
            language, _, rest = rest.partition(b"\x00")
            translated, _, text_bytes = rest.partition(b"\x00")
            try:
                if compressed_flag:
                    text_bytes = zlib.decompress(text_bytes)
                text = text_bytes.decode("utf-8", "ignore")
            except Exception:  # zlib.error 或解码失败
                continue
            texts.setdefault(keyword.decode("latin-1", "ignore"), text)
    return texts


def extract_card_json_from_png(data: bytes) -> Tuple[Dict[str, Any], str]:
    """从 PNG 中解出角色卡 JSON，返回 ``(json 对象, 命中的 chunk keyword)``。"""
    texts = read_png_text_chunks(data)
    if not texts:
        raise CardParseError("这张 PNG 里没有任何文本信息，不是内嵌角色卡的图片")

    for keyword in TEXT_KEYWORDS:
        value = texts.get(keyword)
        if not value:
            continue
        payload = value.strip()
        raw_text = ""
        # 标准做法是 base64(JSON)，但部分工具直接写明文 JSON，两种都兼容
        if payload.startswith("{"):
            raw_text = payload
        else:
            try:
                raw_text = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8", "ignore")
            except (binascii.Error, ValueError):
                raw_text = ""
        if not raw_text.strip():
            continue
        try:
            obj = json.loads(raw_text)
        except (TypeError, ValueError) as exc:
            raise CardParseError(f"PNG 内嵌的 {keyword} 数据不是合法 JSON：{exc}") from exc
        if isinstance(obj, dict):
            return obj, keyword

    available = "、".join(sorted(texts.keys())) or "（无）"
    raise CardParseError(f"PNG 中未找到 chara / ccv3 角色卡数据，现有文本块：{available}")


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def make_gradient_png(
    size: int = 512,
    top_color: Sequence[int] = (94, 78, 168),
    bottom_color: Sequence[int] = (206, 132, 186),
) -> bytes:
    """纯标准库生成一张 ``size x size`` 的对角渐变 RGB 占位图（PNG 字节）。"""
    size = max(16, int(size))
    width = height = size
    top = [max(0, min(255, int(c))) for c in list(top_color)[:3]] or [94, 78, 168]
    bottom = [max(0, min(255, int(c))) for c in list(bottom_color)[:3]] or [206, 132, 186]

    # 每行基础色 + 每列横向偏移，做出对角渐变
    raw = bytearray()
    for y in range(height):
        ratio = y / max(1, height - 1)
        base = [int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)]
        raw.append(0)  # filter type 0（None）
        line = bytearray()
        for x in range(width):
            shift = ((x * 62) // width) - 31  # -31 ~ +31
            line.append(max(0, min(255, base[0] + shift)))
            line.append(max(0, min(255, base[1] + shift // 2)))
            line.append(max(0, min(255, base[2] - shift // 3)))
        raw += line

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8bit truecolor RGB
    idat = zlib.compress(bytes(raw), 9)
    return b"".join(
        [
            PNG_SIGNATURE,
            _chunk(b"IHDR", ihdr),
            _chunk(b"IDAT", idat),
            _chunk(b"IEND", b""),
        ]
    )


def embed_card_json_to_png(
    card: Dict[str, Any],
    size: int = 512,
    keywords: Sequence[str] = (TEXT_KEYWORD_V2,),
) -> bytes:
    """把角色卡 JSON 以 base64 写入 PNG 的 tEXt chunk，返回完整 PNG 字节。"""
    try:
        payload = json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CardParseError(f"角色卡内容无法序列化为 JSON：{exc}") from exc
    encoded = base64.b64encode(payload).decode("ascii")

    data = make_gradient_png(size=size)
    extra = bytearray()
    for keyword in keywords or (TEXT_KEYWORD_V2,):
        key = str(keyword or TEXT_KEYWORD_V2).strip() or TEXT_KEYWORD_V2
        chunk = _chunk(b"tEXt", key.encode("latin-1", "ignore") + b"\x00" + encoded.encode("latin-1", "ignore"))
        extra += chunk

    # 追加到 IEND 之前
    marker = data.rindex(b"IEND") - 4  # IEND chunk 的 length 字段起点
    return data[:marker] + bytes(extra) + data[marker:]


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(_as_str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                return parsed
        return [item.strip() for item in re.split(r"[,，\n]+", text) if item.strip()]
    return [value]


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _as_int(value: Any, default: int = 0) -> int:
    """宽松取整：非数字 / 数字字符串不合法时返回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_card(obj: Any, keyword: str = "") -> Dict[str, Any]:
    """把任意版本的原始角色卡对象规整成统一结构。

    返回::

        {
          "spec": "chara_card_v2",          # 原始 spec 字段
          "spec_version": "2.0",
          "format": "v2",                   # v1 / v2 / v3
          "keyword": "chara",               # 来源 chunk（PNG 才有）
          "data": { ...15 个标准字段... },
          "extra": { ...未识别的字段，导出时原样带回... },
          "fields_hit": ["name", ...],
          "fields_missing": ["scenario", ...],
          "warnings": ["..."]
        }
    """
    if not isinstance(obj, dict):
        raise CardParseError("角色卡内容不是合法的 JSON 对象")

    warnings: List[str] = []
    spec = _as_str(obj.get("spec")).strip()
    raw_data = obj.get("data")
    has_data = isinstance(raw_data, dict)

    if spec:
        lowered = spec.lower()
        if "v3" in lowered:
            fmt = "v3"
        elif "v2" in lowered:
            fmt = "v2"
        elif lowered in {"chara_card_v1", "v1", "1.0"}:
            fmt = "v1"
        else:
            fmt = "v2" if has_data else "v1"
            warnings.append(f"未知的 spec「{spec}」，按 {fmt.upper()} 结构解析")
    elif keyword == TEXT_KEYWORD_V3:
        fmt = "v3"
        warnings.append("缺少 spec 字段，依据 PNG 文本块 ccv3 判定为 V3 结构")
    elif has_data:
        fmt = "v2"
        warnings.append("缺少 spec 字段，按含 data 包裹的 V2 结构解析")
    else:
        fmt = "v1"
        warnings.append("缺少 spec 字段，按 V1 扁平结构解析")

    source = raw_data if has_data else obj
    data: Dict[str, Any] = {}
    fields_hit: List[str] = []
    fields_missing: List[str] = []

    for field in CARD_FIELDS:
        value = source.get(field)
        if field in ("alternate_greetings", "tags"):
            normalized: Any = [_as_str(item) for item in _as_list(value) if _as_str(item).strip()]
        elif field == "character_book":
            normalized = _as_dict(value) or None
        elif field == "extensions":
            normalized = _as_dict(value)
        else:
            normalized = _as_str(value)
        data[field] = normalized
        if normalized:
            fields_hit.append(field)
        else:
            fields_missing.append(field)

    if fmt in ("v2", "v3"):
        for field in ("system_prompt", "post_history_instructions", "creator_notes"):
            if not data.get(field):
                data[field] = ""

    # V1 常见别名：creatorcomment / char_note 等
    if not data["creator_notes"]:
        for alias in ("creatorcomment", "creator_comment", "char_note"):
            if _as_str(obj.get(alias)).strip():
                data["creator_notes"] = _as_str(obj.get(alias))
                fields_hit.append("creator_notes")
                if "creator_notes" in fields_missing:
                    fields_missing.remove("creator_notes")
                warnings.append(f"creator_notes 缺失，已从字段「{alias}」补齐")
                break

    if not any(data.get(field) for field in REQUIRED_ANY):
        raise CardParseError("角色卡缺少可用内容：name / description / first_mes 均为空")

    if not data["name"]:
        data["name"] = "未命名角色"
        warnings.append("角色卡没有 name 字段，已使用默认名「未命名角色」")

    known = set(CARD_FIELDS) | {"spec", "spec_version", "data"}
    extra = {key: value for key, value in (source if fmt == "v1" else obj).items() if key not in known}

    spec_version = _as_str(obj.get("spec_version")).strip()
    if not spec_version:
        spec_version = V1_SPEC if fmt == "v1" else (V3_SPEC_VERSION if fmt == "v3" else V2_SPEC_VERSION)

    return {
        "spec": spec or (V3_SPEC if fmt == "v3" else (V2_SPEC if fmt == "v2" else V1_SPEC)),
        "spec_version": spec_version,
        "format": fmt,
        "keyword": keyword,
        "data": data,
        "extra": extra,
        "fields_hit": fields_hit,
        "fields_missing": fields_missing,
        "warnings": warnings,
    }


def parse_card_payload(raw: Any, filename: str = "") -> Dict[str, Any]:
    """解析角色卡文件内容（JSON 文本 / PNG 字节均可），返回 ``normalize_card`` 结果。"""
    if raw is None or (isinstance(raw, (bytes, bytearray)) and not raw):
        raise CardParseError("上传的文件为空")

    name = str(filename or "").lower()
    if isinstance(raw, (bytes, bytearray)):
        payload = bytes(raw)
        if payload.startswith(PNG_SIGNATURE):
            obj, keyword = extract_card_json_from_png(payload)
            return normalize_card(obj, keyword=keyword)
        if name.endswith(".png"):
            raise CardParseError("扩展名是 .png，但文件内容不是有效的 PNG")
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = payload.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise CardParseError("文件既不是 PNG，也无法按 UTF-8 / GB18030 解码为 JSON 文本") from exc
    else:
        text = _as_str(raw)

    text = text.strip()
    if not text:
        raise CardParseError("角色卡内容为空")
    try:
        obj = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise CardParseError(f"角色卡不是合法的 JSON：{exc}") from exc
    return normalize_card(obj)


# --------------------------------------------------------------------------
# 映射：角色卡 -> 本项目 Persona
# --------------------------------------------------------------------------
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2764]+",
)

_TSundere_HINTS = ("傲娇", "别扭", "嘴硬", "骄", "凶", "毒舌", "冷淡", "腹黑")
_GENTLE_HINTS = ("温柔", "体贴", "耐心", "包容", "治愈", "柔和", "安静")
_SHARP_HINTS = ("毒舌", "犀利", "强势", "理智", "冷静", "直白", "嘲讽")
_CLINGY_HINTS = ("黏", "粘", "依赖", "撒娇", "怕孤单", "占有")
_PROACTIVE_HINTS = ("主动", "热情", "开朗", "活泼", "话多", "外向")


def _infer_sliders(text: str) -> Dict[str, int]:
    """按人设描述里的关键词粗略推断五维数值（纯启发式，可被用户在前端手改）。"""
    try:
        from app.services.persona.extractor import DEFAULT_SLIDERS as _BASE
    except Exception:  # pragma: no cover - 兜底，避免循环导入导致失败
        _BASE = {"gentle": 60, "tsundere": 40, "sharp": 40, "clingy": 40, "proactive": 50}

    sliders = {key: int(value) for key, value in dict(_BASE).items()}
    rules = (
        ("tsundere", _TSundere_HINTS, 34),
        ("gentle", _GENTLE_HINTS, 24),
        ("sharp", _SHARP_HINTS, 26),
        ("clingy", _CLINGY_HINTS, 24),
        ("proactive", _PROACTIVE_HINTS, 24),
    )
    haystack = str(text or "")
    for key, hints, delta in rules:
        if any(hint in haystack for hint in hints):
            sliders[key] = max(0, min(100, sliders.get(key, 50) + delta))
    return sliders


def split_mes_example(text: str, limit: int = 20) -> List[Dict[str, str]]:
    """把 ``mes_example``（``<START>`` 分隔 + ``{{user}}:`` / ``{{char}}:`` 行）拆成样例对话对。"""
    content = _as_str(text)
    if not content.strip():
        return []

    pairs: List[Dict[str, str]] = []
    for block in re.split(r"<START>", content, flags=re.IGNORECASE):
        user_buf: List[str] = []
        reply_buf: List[str] = []
        current = ""

        def flush() -> None:
            if user_buf or reply_buf:
                pairs.append(
                    {
                        "user": "\n".join(line for line in user_buf if line).strip(),
                        "reply": "\n".join(line for line in reply_buf if line).strip(),
                    }
                )

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matched = re.match(r"^(?P<who>\{\{user\}\}|\{\{char\}\}|[^:：\n]{1,32})[:：]\s*(?P<text>.*)$", line)
            if matched:
                who = matched.group("who").strip().lower()
                content_part = matched.group("text").strip()
                is_user = who in ("{{user}}", "user", "我", "用户")
                is_char = who in ("{{char}}", "char", "character", "bot", "对方", "角色")
                if is_user:
                    if reply_buf:
                        flush()
                        user_buf, reply_buf = [], []
                    current = "user"
                elif is_char:
                    if current == "user" and (user_buf or reply_buf):
                        pass
                    current = "char"
                else:
                    # 未标记说话人：沿用上一个角色
                    current = current or "char"
                if current == "user":
                    user_buf.append(content_part)
                else:
                    reply_buf.append(content_part)
            else:
                if current == "user":
                    user_buf.append(line)
                else:
                    reply_buf.append(line)

        flush()
        if len(pairs) >= limit:
            break

    result: List[Dict[str, str]] = []
    for pair in pairs[:limit]:
        if pair["user"] or pair["reply"]:
            result.append(pair)
    return result


def build_mes_example(sample_dialogues: Iterable[Dict[str, Any]], limit: int = 20) -> str:
    """把项目内的样例对话列表还原成酒馆 ``mes_example`` 文本。"""
    blocks: List[str] = []
    for item in list(sample_dialogues or [])[:limit]:
        if not isinstance(item, dict):
            continue
        user = _as_str(item.get("user") or item.get("q")).strip()
        reply = _as_str(item.get("reply") or item.get("a")).strip()
        lines: List[str] = []
        if user:
            lines.append(f"{{{{user}}}}: {user}")
        if reply:
            lines.append(f"{{{{char}}}}: {reply}")
        if lines:
            blocks.append("\n".join(lines))
    return "\n<START>\n".join(blocks)


def _emoji_habits(text: str, limit: int = 3) -> List[str]:
    counter: Dict[str, int] = {}
    for match in _EMOJI_RE.findall(str(text or "")):
        counter[match] = counter.get(match, 0) + 1
    return [key for key, _ in sorted(counter.items(), key=lambda kv: -kv[1])[:limit]]


def card_to_persona(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """角色卡（``normalize_card`` 结果）→ 本项目 Persona 字段集合。

    返回的 ``worldbook`` 为待写入的 ``WorldBookEntry`` 字段列表（不含 persona_id）。
    """
    if not isinstance(parsed, dict) or "data" not in parsed:
        raise CardParseError("角色卡数据结构无效，无法映射到人格")

    data = parsed.get("data") or {}
    name = _as_str(data.get("name")).strip() or "未命名角色"
    description = _as_str(data.get("description")).strip()
    personality = _as_str(data.get("personality")).strip()
    scenario = _as_str(data.get("scenario")).strip()
    first_mes = _as_str(data.get("first_mes")).strip()
    mes_example = _as_str(data.get("mes_example")).strip()
    creator_notes = _as_str(data.get("creator_notes")).strip()
    creator = _as_str(data.get("creator")).strip()
    character_version = _as_str(data.get("character_version")).strip() or "1.0"
    system_prompt = _as_str(data.get("system_prompt")).strip()
    post_history = _as_str(data.get("post_history_instructions")).strip()
    alternate_greetings = [_as_str(item).strip() for item in _as_list(data.get("alternate_greetings")) if _as_str(item).strip()]
    tags = [_as_str(item).strip() for item in _as_list(data.get("tags")) if _as_str(item).strip()]

    extra_bits: List[str] = []
    if description:
        extra_bits.append(description)
    if personality:
        extra_bits.append(f"性格：{personality}")
    if scenario:
        extra_bits.append(f"场景：{scenario}")
    if not extra_bits and creator_notes:
        extra_bits.append(creator_notes)
    extra_description = "\n".join(extra_bits).strip()

    dialogues = split_mes_example(mes_example)
    reply_lengths = [len(item["reply"]) for item in dialogues if item.get("reply")]
    avg_length = round(sum(reply_lengths) / len(reply_lengths), 1) if reply_lengths else 0.0

    card: Dict[str, Any] = {
        "nickname": name,
        "message_count": 0,
        "avg_length": avg_length,
        "top_phrases": [],
        "emoji_habits": _emoji_habits(first_mes + description + personality),
        "punctuation_habits": [],
        "sample_dialogues": dialogues,
        "extra_description": extra_description,
        "source_speaker": creator,
        "st_meta": {
            "spec": parsed.get("spec"),
            "spec_version": parsed.get("spec_version"),
            "format": parsed.get("format"),
            "keyword": parsed.get("keyword"),
            "description": description,
            "personality": personality,
            "scenario": scenario,
            "system_prompt": system_prompt,
            "post_history_instructions": post_history,
            "alternate_greetings": alternate_greetings,
            "creator": creator,
            "creator_notes": creator_notes,
            "character_version": character_version,
            "tags": tags,
            "extensions": _as_dict(data.get("extensions")),
            "extra": parsed.get("extra") or {},
        },
    }

    greeting = first_mes or (alternate_greetings[0] if alternate_greetings else "")
    if not greeting:
        greeting = f"（{name}）……你好，我是{name}。"
        parsed.setdefault("warnings", []).append("角色卡没有 first_mes，已生成默认开场白")

    summary = {
        "spec": parsed.get("spec"),
        "spec_version": parsed.get("spec_version"),
        "format": parsed.get("format"),
        "keyword": parsed.get("keyword") or "",
        "fields_hit": list(parsed.get("fields_hit") or []),
        "fields_missing": list(parsed.get("fields_missing") or []),
        "alternate_greetings": len(alternate_greetings),
        "sample_dialogues": len(dialogues),
        "worldbook_entries": len(card_to_worldbook_entries(data.get("character_book"))),
        "warnings": list(parsed.get("warnings") or []),
    }

    return {
        "name": name[:64],
        "avatar_emoji": _first_emoji(card["emoji_habits"]) or "💠",
        "relation": "女友",
        "nickname_for_user": "你",
        "greeting": greeting,
        "source": "card_import",
        "creator_notes": creator_notes or (f"来自酒馆角色卡，作者：{creator}" if creator else ""),
        "tags": tags,
        "character_version": character_version,
        "card_spec": _as_str(parsed.get("spec")).strip() or f"chara_card_{parsed.get('format') or 'v2'}",
        "extensions": _as_dict(data.get("extensions")),
        "persona_card": card,
        "sliders": _infer_sliders(" ".join([description, personality, scenario, first_mes])),
        "worldbook": card_to_worldbook_entries(data.get("character_book")),
        "summary": summary,
    }


def _first_emoji(items: Iterable[str]) -> str:
    for item in items or []:
        text = _as_str(item)
        if text:
            return text
    return ""


def card_to_worldbook_entries(character_book: Any) -> List[Dict[str, Any]]:
    """``character_book`` → 世界书条目字段列表（可直接建 ``WorldBookEntry``）。"""
    book = _as_dict(character_book)
    raw_entries = book.get("entries")
    if not isinstance(raw_entries, list):
        return []

    result: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            continue
        keys = [_as_str(key).strip() for key in _as_list(item.get("keys")) if _as_str(key).strip()]
        content = _as_str(item.get("content")).strip()
        if not content:
            continue

        extensions = _as_dict(item.get("extensions"))
        position_raw = item.get("position")
        position = "before_char"
        depth = 4

        if position_raw is not None and not isinstance(position_raw, str):
            position = "at_depth"
            depth = _as_int(extensions.get("depth") or item.get("depth"), 4)
        else:
            text = _as_str(position_raw).strip().lower()
            if text in _POSITION_ALIASES:
                position = _POSITION_ALIASES[text]
                if position == "at_depth":
                    depth = _as_int(extensions.get("depth") or item.get("depth"), 4)
            elif extensions:
                ext_pos = _as_str(extensions.get("position")).strip().lower()
                if ext_pos in ("2", "3", "4", "at_depth"):
                    position = "at_depth"
                    depth = _as_int(extensions.get("depth"), 4)
                elif ext_pos == "1":
                    position = "after_char"

        priority = item.get("priority")
        if priority is None:
            priority = item.get("insertion_order")
        try:
            priority_value = int(priority)
        except (TypeError, ValueError):
            priority_value = 100
        if priority_value < 0:
            priority_value = 100

        token_budget = extensions.get("token_budget")
        try:
            token_budget_value = max(0, int(token_budget))
        except (TypeError, ValueError):
            token_budget_value = 0

        name = _as_str(item.get("name") or item.get("comment")).strip()
        result.append(
            {
                "keys": keys,
                "content": content,
                "enabled": bool(item.get("enabled", True)),
                "constant": bool(item.get("constant", False)),
                "case_sensitive": bool(item.get("case_sensitive", False)),
                "priority": priority_value,
                "position": position,
                "depth": max(0, depth),
                "token_budget": token_budget_value,
                "comment": (name or f"角色书条目 {index + 1}")[:128],
                "source": "card_import",
            }
        )
    return result


# --------------------------------------------------------------------------
# 生成：本项目 Persona -> 角色卡
# --------------------------------------------------------------------------
def worldbook_entries_to_character_book(entries: Iterable[Any]) -> Dict[str, Any]:
    """世界书条目 → 酒馆 ``character_book`` 结构。"""
    items: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries or []):
        if isinstance(entry, dict):
            keys = [_as_str(key).strip() for key in _as_list(entry.get("keys")) if _as_str(key).strip()]
            content = _as_str(entry.get("content")).strip()
            enabled = bool(entry.get("enabled", True))
            constant = bool(entry.get("constant", False))
            case_sensitive = bool(entry.get("case_sensitive", False))
            priority = entry.get("priority", 100)
            position = _as_str(entry.get("position")).strip() or "before_char"
            depth = entry.get("depth", 4)
            token_budget = entry.get("token_budget", 0)
            comment = _as_str(entry.get("comment")).strip()
        else:
            keys = list(entry.key_list())
            content = _as_str(getattr(entry, "content", "")).strip()
            enabled = bool(getattr(entry, "enabled", True))
            constant = bool(getattr(entry, "constant", False))
            case_sensitive = bool(getattr(entry, "case_sensitive", False))
            priority = getattr(entry, "priority", 100)
            position = _as_str(getattr(entry, "position", "before_char")) or "before_char"
            depth = getattr(entry, "depth", 4)
            token_budget = getattr(entry, "token_budget", 0)
            comment = _as_str(getattr(entry, "comment", "")).strip()

        if not content:
            continue
        position_code = 0 if position == "before_char" else 1
        if position == "at_depth":
            position_code = 4
        try:
            priority_value = int(priority)
        except (TypeError, ValueError):
            priority_value = 100
        try:
            depth_value = max(0, int(depth))
        except (TypeError, ValueError):
            depth_value = 4
        try:
            budget_value = max(0, int(token_budget))
        except (TypeError, ValueError):
            budget_value = 0

        items.append(
            {
                "id": index,
                "keys": keys,
                "secondary_keys": [],
                "comment": comment,
                "name": comment or f"世界书条目 {index + 1}",
                "content": content,
                "constant": constant,
                "selective": not constant,
                "insertion_order": priority_value,
                "priority": priority_value,
                "enabled": enabled,
                "position": position,
                "case_sensitive": case_sensitive,
                "extensions": {
                    "position": position_code,
                    "depth": depth_value,
                    "token_budget": budget_value,
                },
            }
        )
    return {"name": "角色书", "description": "由 Cyber Girlfriend 导出的世界书", "entries": items}


def persona_to_card(
    persona: Any,
    entries: Optional[Iterable[Any]] = None,
    spec: str = "v2",
) -> Dict[str, Any]:
    """本项目 Persona（ORM 对象或 dict）→ 角色卡 JSON（``spec`` 取 ``v1`` / ``v2`` / ``v3``）。"""
    def get(field: str, default: Any = "") -> Any:
        if isinstance(persona, dict):
            return persona.get(field, default)
        return getattr(persona, field, default)

    def card_dict() -> Dict[str, Any]:
        if isinstance(persona, dict):
            value = persona.get("persona_card") or persona.get("card") or {}
        else:
            value = persona.card() if hasattr(persona, "card") else {}
        return value if isinstance(value, dict) else {}

    card = card_dict()
    st_meta = card.get("st_meta") if isinstance(card.get("st_meta"), dict) else {}

    name = _as_str(get("name")).strip() or "未命名角色"
    greeting = _as_str(get("greeting")).strip()
    description = _as_str(st_meta.get("description")).strip() or _as_str(card.get("extra_description")).strip()
    personality = _as_str(st_meta.get("personality")).strip()
    if not personality:
        sliders = get("sliders", {}) or {}
        if isinstance(sliders, dict) and sliders:
            personality = "；".join(f"{key}={value}" for key, value in sliders.items())
    scenario = _as_str(st_meta.get("scenario")).strip()
    mes_example = _as_str(st_meta.get("mes_example")).strip() or build_mes_example(card.get("sample_dialogues") or [])
    creator_notes = _as_str(get("creator_notes")).strip() or _as_str(st_meta.get("creator_notes")).strip()
    creator = _as_str(st_meta.get("creator")).strip()
    character_version = _as_str(get("character_version")).strip() or _as_str(st_meta.get("character_version")).strip() or "1.0"

    if isinstance(persona, dict):
        tags = [str(item) for item in (persona.get("tags") or [])]
        extensions = dict(persona.get("extensions") or {})
    else:
        tags = persona.tag_list() if hasattr(persona, "tag_list") else []
        extensions = persona.extension_dict() if hasattr(persona, "extension_dict") else {}

    st_extensions = _as_dict(st_meta.get("extensions"))
    merged_extensions = {**st_extensions, **extensions}
    character_book = st_meta.get("character_book")
    entry_list = list(entries or [])
    if entry_list:
        character_book = worldbook_entries_to_character_book(entry_list)
    elif not isinstance(character_book, dict):
        character_book = None

    alternate_greetings = [_as_str(item).strip() for item in _as_list(st_meta.get("alternate_greetings")) if _as_str(item).strip()]
    # 开场白变化后，把原 first_mes 降级进 alternate_greetings，避免信息丢失
    original_first = _as_str(st_meta.get("first_mes")).strip()
    if original_first and greeting and original_first != greeting:
        alternate_greetings = [original_first] + [item for item in alternate_greetings if item != original_first]

    data: Dict[str, Any] = {
        "name": name,
        "description": description,
        "personality": personality,
        "scenario": scenario,
        "first_mes": greeting,
        "mes_example": mes_example,
        "creator_notes": creator_notes,
        "system_prompt": _as_str(st_meta.get("system_prompt")).strip(),
        "post_history_instructions": _as_str(st_meta.get("post_history_instructions")).strip(),
        "alternate_greetings": alternate_greetings,
        "character_book": character_book,
        "tags": tags,
        "creator": creator,
        "character_version": character_version,
        "extensions": merged_extensions,
    }

    spec_key = str(spec or "v2").strip().lower()
    if spec_key in ("v1", "1"):
        flat = {
            key: data.get(key, "")
            for key in ("name", "description", "personality", "scenario", "first_mes", "mes_example")
        }
        flat["creatorcomment"] = data["creator_notes"]
        flat["tags"] = data["tags"]
        return flat

    extra = _as_dict(st_meta.get("extra"))
    for key, value in extra.items():
        data.setdefault(key, value)

    if spec_key in ("v3", "3"):
        return {"spec": V3_SPEC, "spec_version": V3_SPEC_VERSION, "data": data}
    return {"spec": V2_SPEC, "spec_version": V2_SPEC_VERSION, "data": data}


def build_card_png(
    card: Dict[str, Any],
    size: int = 512,
    spec: Optional[str] = None,
) -> bytes:
    """角色卡 JSON → 内嵌角色卡的 PNG。

    默认写入 ``chara`` chunk；当卡为 V3（或 ``spec`` 指定 v3）时额外写入 ``ccv3``，
    保证新旧版酒馆都能识别。
    """
    spec_key = str(spec or card.get("spec") or "").strip().lower()
    keywords: Tuple[str, ...] = (TEXT_KEYWORD_V2,)
    if "v3" in spec_key:
        keywords = (TEXT_KEYWORD_V3, TEXT_KEYWORD_V2)
    return embed_card_json_to_png(card, size=size, keywords=keywords)


__all__ = [
    "CARD_FIELDS",
    "CardParseError",
    "PNG_SIGNATURE",
    "TEXT_KEYWORDS",
    "TEXT_KEYWORD_V2",
    "TEXT_KEYWORD_V3",
    "V2_SPEC",
    "V3_SPEC",
    "build_card_png",
    "build_mes_example",
    "card_to_persona",
    "card_to_worldbook_entries",
    "embed_card_json_to_png",
    "extract_card_json_from_png",
    "make_gradient_png",
    "normalize_card",
    "parse_card_payload",
    "persona_to_card",
    "read_png_text_chunks",
    "split_mes_example",
    "worldbook_entries_to_character_book",
]
