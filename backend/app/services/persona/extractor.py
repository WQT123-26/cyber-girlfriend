"""人格提取器：从聊天记录里"读懂"一个人。

纯启发式实现，不依赖任何 NLP 库：
    * 口头禅        -> 2~4 字高频片段 Top10
    * emoji 习惯    -> emoji 字符频次
    * 标点习惯      -> 高频标点及次数
    * 平均句长      -> 字符均值
    * 样例对话      -> 从真实对话中截取 20~50 组（前一条是对方 + 这条是 TA）
    * 风格滑块      -> gentle / tsundere / sharp / clingy / proactive 关键词与句式占比打分
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_SLIDERS: Dict[str, int] = {
    "gentle": 50,
    "tsundere": 50,
    "sharp": 50,
    "clingy": 50,
    "proactive": 50,
}

_CJK_RUN = re.compile(r"[\u4e00-\u9fa5]+")
_TOKEN = re.compile(r"[\u4e00-\u9fa5a-zA-Z0-9]+")
_CJK_ONLY = re.compile(r"^[\u4e00-\u9fa5]+$")
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U0001f000-\U0001f2ff"
    "\U00002600-\U000027bf"
    "\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff"
    "\u2764\u2665\u2661\u2728\u2b50\u2705\u274c\u23f0"
    "]"
)
_PUNCT = ["～", "~", "！", "!", "？", "?", "。", "…", "，", "、", ":) ", "^_^"]

_MIN_SAMPLE_DIALOGUES = 20
_MAX_SAMPLE_DIALOGUES = 50

_KEYWORDS: Dict[str, List[str]] = {
    "gentle": [
        "呀", "呢", "啦", "哦", "嗯嗯", "好的", "谢谢", "辛苦", "抱抱", "别急",
        "慢慢来", "没事的", "我陪你", "注意身体", "早点睡", "乖", "暖",
    ],
    "tsundere": [
        "哼", "才不是", "才没有", "谁要", "讨厌", "笨蛋", "懒得", "随便你",
        "不理你", "略略略", "想得美", "谁管你", "才怪", "切",
    ],
    "sharp": [
        "闭嘴", "滚", "傻", "蠢", "烦", "有病", "无语", "幼稚", "别废话",
        "少来", "废", "恶心", "烦死",
    ],
    "clingy": [
        "想你", "抱抱", "亲亲", "陪我", "别走", "不要走", "在干嘛", "理我",
        "么么", "爱你", "黏", "陪着我", "不许",
    ],
    "proactive": [
        "?", "？", "吗", "呢", "怎么", "为什么", "要不要", "一起", "我们去",
        "你猜", "要不要我", "我建议", "要不",
    ],
}


def _iter_ngrams(text: str, low: int = 2, high: int = 4) -> Iterable[str]:
    for run in _CJK_RUN.findall(text or ""):
        length = len(run)
        for size in range(low, high + 1):
            if length < size:
                continue
            for index in range(length - size + 1):
                yield run[index : index + size]


def _ratio(messages: List[str], keywords: List[str]) -> float:
    if not messages:
        return 0.0
    hits = 0
    for text in messages:
        if any(word in text for word in keywords):
            hits += 1
    return hits / float(len(messages))


def _score(ratio: float, base: int = 12, scale: int = 420) -> int:
    value = int(base + ratio * scale)
    return max(0, min(100, value))


def score_sliders(messages: List[str]) -> Dict[str, int]:
    """按关键词命中比例给 5 个风格维度打分（0~100）。"""
    sliders: Dict[str, int] = {}
    for key, words in _KEYWORDS.items():
        sliders[key] = _score(_ratio(messages, words))

    # 平均句长也会影响风格：话长偏温柔/黏人，话短偏毒舌/傲娇
    if messages:
        avg_len = sum(len(m) for m in messages) / float(len(messages))
        if avg_len >= 18:
            sliders["gentle"] = min(100, sliders["gentle"] + 8)
            sliders["clingy"] = min(100, sliders["clingy"] + 5)
        elif avg_len <= 8:
            sliders["sharp"] = min(100, sliders["sharp"] + 8)
            sliders["tsundere"] = min(100, sliders["tsundere"] + 6)
    return sliders


def _top_phrases(messages: List[str], top: int = 10) -> List[str]:
    counter: Dict[str, int] = {}
    for text in messages[:1500]:
        for gram in _iter_ngrams(text[:200]):
            if _CJK_ONLY.match(gram):
                counter[gram] = counter.get(gram, 0) + 1
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    result: List[str] = []
    for gram, count in ranked:
        if count < 2:
            break
        if any(gram in existing or existing in gram for existing in result):
            continue
        result.append(gram)
        if len(result) >= top:
            break
    return result


def _emoji_habits(messages: List[str], top: int = 4) -> List[str]:
    counter: Dict[str, int] = {}
    for text in messages[:3000]:
        for char in _EMOJI.findall(text):
            counter[char] = counter.get(char, 0) + 1
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [char for char, _ in ranked[:top]]


def _punctuation_habits(messages: List[str], top: int = 5) -> List[str]:
    counter: Dict[str, int] = {}
    joined = "\n".join(messages[:3000])
    for mark in _PUNCT:
        mark = mark.strip()
        if not mark:
            continue
        count = joined.count(mark)
        if count:
            counter[mark] = count
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [f"{mark} x{count}" for mark, count in ranked[:top]]


def _sample_dialogues(messages: List[Dict[str, str]], speaker: str) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    for index, item in enumerate(messages):
        if item.get("speaker") != speaker:
            continue
        if index == 0:
            continue
        previous = messages[index - 1]
        if previous.get("speaker") == speaker:
            continue
        user_text = (previous.get("content") or "").strip()
        reply_text = (item.get("content") or "").strip()
        if not user_text or not reply_text:
            continue
        if len(user_text) > 120:
            user_text = user_text[:120]
        if len(reply_text) > 160:
            reply_text = reply_text[:160]
        pairs.append({"user": user_text, "reply": reply_text})

    if len(pairs) <= _MAX_SAMPLE_DIALOGUES:
        return pairs

    # 均匀采样，保证覆盖整段对话
    step = len(pairs) / float(_MAX_SAMPLE_DIALOGUES)
    sampled = [pairs[int(i * step)] for i in range(_MAX_SAMPLE_DIALOGUES)]
    return sampled


def extract_persona_card(
    messages: List[Dict[str, str]],
    speaker: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """提取人设卡。"""
    own_texts: List[str] = [
        (m.get("content") or "").strip()
        for m in messages
        if m.get("speaker") == speaker and (m.get("content") or "").strip()
    ]
    avg_length = round(sum(len(t) for t in own_texts) / float(len(own_texts)), 1) if own_texts else 0.0

    return {
        "nickname": display_name or speaker,
        "message_count": len(own_texts),
        "avg_length": avg_length,
        "top_phrases": _top_phrases(own_texts),
        "emoji_habits": _emoji_habits(own_texts),
        "punctuation_habits": _punctuation_habits(own_texts),
        "sample_dialogues": _sample_dialogues(messages, speaker),
        "extra_description": "",
        "source_speaker": speaker,
    }


def extract_from_messages(
    messages: List[Dict[str, str]],
    speaker: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """一次性产出人设卡 + 滑块。"""
    card = extract_persona_card(messages, speaker, display_name)
    own_texts = [
        (m.get("content") or "").strip()
        for m in messages
        if m.get("speaker") == speaker and (m.get("content") or "").strip()
    ]
    card["message_count"] = len(own_texts)
    return {"persona_card": card, "sliders": score_sliders(own_texts), "speaker": speaker}


__all__ = [
    "DEFAULT_SLIDERS",
    "extract_from_messages",
    "extract_persona_card",
    "score_sliders",
]
