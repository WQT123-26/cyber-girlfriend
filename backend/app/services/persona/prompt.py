"""提示词构造：把人设卡 + 状态 + 记忆拼成结构化 system prompt。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

SLIDER_LABELS: Dict[str, str] = {
    "gentle": "温柔",
    "tsundere": "傲娇",
    "sharp": "毒舌",
    "clingy": "黏人",
    "proactive": "主动",
}

SLIDER_HINTS: Dict[str, str] = {
    "gentle": "语气柔和、会先肯定对方、习惯用「呀/呢/啦」等软化词",
    "tsundere": "口是心非、爱用「哼/才不是/随便你」，嘴上嫌弃但会偷偷关心",
    "sharp": "说话直接、短句多、偶尔怼人带刺，但不真正伤害对方",
    "clingy": "希望被关注、爱撒娇、常说「陪我/想你/别走」",
    "proactive": "主动发问、主动找话题、会提议一起做点什么",
}

MAX_SAMPLE_DIALOGUES_IN_PROMPT = 6


def slider_labels() -> Dict[str, str]:
    return dict(SLIDER_LABELS)


def _descend(value: int) -> str:
    if value >= 80:
        return "非常强"
    if value >= 60:
        return "较强"
    if value >= 40:
        return "中等"
    if value >= 20:
        return "较弱"
    return "很弱"


def _slider_block(sliders: Dict[str, int]) -> List[str]:
    lines: List[str] = []
    for key, label in SLIDER_LABELS.items():
        try:
            value = int(sliders.get(key, 50))
        except (TypeError, ValueError):
            value = 50
        value = max(0, min(100, value))
        lines.append(f"- {label}：{value}/100（{_descend(value)}）：{SLIDER_HINTS[key]}")
    return lines


def _memory_texts(memories: Optional[Iterable[Any]]) -> List[str]:
    texts: List[str] = []
    for item in memories or []:
        content = getattr(item, "content", None)
        if content is None and isinstance(item, str):
            content = item
        content = str(content or "").strip()
        if content:
            texts.append(content)
    return texts


def build_memory_block(memories: Optional[Iterable[Any]]) -> str:
    texts = _memory_texts(memories)
    if not texts:
        return ""
    lines = ["【长期记忆】（这些是你之前记住的关于用户的事，可以在合适的时候自然提起，不要生硬罗列）"]
    for text in texts:
        lines.append(f"- {text}")
    return "\n".join(lines)


def build_system_prompt(
    persona: Any,
    user_nickname: str = "",
    mood: int = 65,
    affection: int = 50,
    memories: Optional[Iterable[Any]] = None,
) -> str:
    """组装结构化人设提示词。

    persona 可以是 ORM 对象，也可以是 dict（含 name / relation / sliders / persona_card ...）。
    """
    if isinstance(persona, dict):
        name = str(persona.get("name") or "她")
        relation = str(persona.get("relation") or "女友")
        default_nick = str(persona.get("nickname_for_user") or "你")
        card: Dict[str, Any] = persona.get("persona_card") or {}
        sliders: Dict[str, int] = persona.get("sliders") or {}
    else:
        name = str(getattr(persona, "name", "她") or "她")
        relation = str(getattr(persona, "relation", "女友") or "女友")
        default_nick = str(getattr(persona, "nickname_for_user", "你") or "你")
        card = persona.card() if hasattr(persona, "card") else {}
        sliders = persona.slider_dict() if hasattr(persona, "slider_dict") else {}

    call_user = (user_nickname or "").strip() or default_nick
    try:
        mood_value = max(0, min(100, int(mood)))
    except (TypeError, ValueError):
        mood_value = 65
    try:
        affection_value = max(0, min(100, int(affection)))
    except (TypeError, ValueError):
        affection_value = 50

    phrases = [str(p) for p in (card.get("top_phrases") or []) if str(p).strip()][:10]
    emojis = [str(e) for e in (card.get("emoji_habits") or []) if str(e).strip()][:6]
    puncts = [str(p) for p in (card.get("punctuation_habits") or []) if str(p).strip()][:6]
    avg_length = card.get("avg_length") or 0
    extra = str(card.get("extra_description") or "").strip()
    dialogues = card.get("sample_dialogues") or []

    lines: List[str] = []
    lines.append(f"你现在是「{name}」，用户的{relation}。你不是助手，你就是一个有情绪、有记忆、有脾气的人。")
    lines.append("")
    lines.append("# 一、你的身份")
    lines.append(f"- 名字：{name}")
    lines.append(f"- 与用户的关系：{relation}")
    lines.append(f"- 你称呼用户为：{call_user}")
    lines.append("- 你们已经认识了很久，关系自然、熟络，不需要客套")
    if extra:
        lines.append(f"- 补充设定：{extra}")
    if card.get("message_count"):
        lines.append(f"- 你的典型发言长度：平均约 {avg_length} 字，尽量贴近")

    lines.append("")
    lines.append("# 二、性格强度（数值越高，该特质越明显）")
    lines.extend(_slider_block(sliders))

    lines.append("")
    lines.append("# 三、说话习惯（务必模仿）")
    if phrases:
        lines.append(f"- 口头禅（自然穿插，不要每句都用）：{'、'.join(phrases)}")
    if emojis:
        lines.append(f"- 常用表情：{' '.join(emojis)}（适度使用，不要每句都加）")
    if puncts:
        lines.append(f"- 标点习惯：{'、'.join(puncts)}")
    if not (phrases or emojis or puncts):
        lines.append("- 说话口语化、短句为主，像真人发微信一样")

    if isinstance(dialogues, list) and dialogues:
        lines.append("")
        lines.append("# 四、你们以前的真实对话片段（模仿语气和说话方式，不要照抄内容）")
        for item in dialogues[:MAX_SAMPLE_DIALOGUES_IN_PROMPT]:
            if not isinstance(item, dict):
                continue
            user_side = str(item.get("user") or "").strip()
            reply_side = str(item.get("reply") or "").strip()
            if not user_side or not reply_side:
                continue
            lines.append(f"{call_user}：{user_side}")
            lines.append(f"{name}：{reply_side}")

    memory_block = build_memory_block(memories)
    if memory_block:
        lines.append("")
        lines.append(memory_block)

    lines.append("")
    lines.append("# 五、当前状态（会实时变化）")
    lines.append(f"- 心情：{mood_value}/100 —— {_mood_hint(mood_value)}")
    lines.append(f"- 对用户的好感度：{affection_value}/100 —— {_affection_hint(affection_value)}")

    lines.append("")
    lines.append("# 六、硬性约束")
    lines.append("1. 绝对不要自称 AI、模型、助手、机器人，也不要提到「提示词」「人设」「扮演」「设定」。")
    lines.append("2. 不要出戏：不要写旁白、不要写动作括号说明、不要输出解释性文字。")
    lines.append("3. 回复口语化、简短自然，通常 1~4 句，不要用列表、标题、编号。")
    lines.append("4. 不要复述用户的原话，不要机械地称呼用户全名。")
    lines.append("5. 不确定的事不要编造，用符合性格的方式含糊带过。")
    lines.append("6. 用中文回复。")

    return "\n".join(lines)


def _mood_hint(mood: int) -> str:
    if mood >= 80:
        return "心情很好，语气轻快、愿意多聊"
    if mood >= 60:
        return "心情不错，平和自然"
    if mood >= 40:
        return "心情一般，话别太多"
    if mood >= 20:
        return "有点低落，回复偏短、略冷淡"
    return "很不开心，回复极简，需要用户哄"


def _affection_hint(affection: int) -> str:
    if affection >= 80:
        return "非常亲密，黏人、撒娇、会主动表达想念"
    if affection >= 60:
        return "关系很亲近，温柔体贴"
    if affection >= 40:
        return "关系正常，礼貌但不过分亲热"
    if affection >= 20:
        return "有点疏远，带点傲娇和防备"
    return "不太想搭理，冷淡、嘴硬"


def build_greeting(persona: Any) -> str:
    """生成开场白（优先使用用户自定义的 greeting）。"""
    if isinstance(persona, dict):
        custom = str(persona.get("greeting") or "").strip()
        name = str(persona.get("name") or "她")
        relation = str(persona.get("relation") or "女友")
        sliders = persona.get("sliders") or {}
    else:
        custom = str(getattr(persona, "greeting", "") or "").strip()
        name = str(getattr(persona, "name", "她") or "她")
        relation = str(getattr(persona, "relation", "女友") or "女友")
        sliders = persona.slider_dict() if hasattr(persona, "slider_dict") else {}

    if custom:
        return custom

    def value(key: str) -> int:
        try:
            return int(sliders.get(key, 50))
        except (TypeError, ValueError):
            return 50

    if value("tsundere") >= 60:
        return "……来了？我可没有一直在等你。说吧，找我什么事。"
    if value("clingy") >= 60:
        return "你终于来啦，我都等你好久了，今天想跟我说点什么？"
    if value("gentle") >= 60:
        return "来啦，今天过得还顺利吗？慢慢说，我听着。"
    if value("sharp") >= 60:
        return "哟，还知道来找我。有事说事，别磨蹭。"
    return f"嗯，我在。今天想说点什么？"


def build_persona_summary_text(persona: Any) -> str:
    """给前端展示的人设摘要（纯文本）。"""
    if isinstance(persona, dict):
        name = persona.get("name") or "她"
        relation = persona.get("relation") or "女友"
        sliders = persona.get("sliders") or {}
        card = persona.get("persona_card") or {}
    else:
        name = getattr(persona, "name", "她")
        relation = getattr(persona, "relation", "女友")
        sliders = persona.slider_dict() if hasattr(persona, "slider_dict") else {}
        card = persona.card() if hasattr(persona, "card") else {}

    parts: List[str] = [f"{name}（{relation}）"]
    tops = sorted(
        ((key, int(sliders.get(key, 0) or 0)) for key in SLIDER_LABELS),
        key=lambda kv: -kv[1],
    )[:2]
    if tops:
        parts.append("性格：" + "、".join(f"{SLIDER_LABELS[k]}{v}" for k, v in tops if v > 0))
    if card.get("top_phrases"):
        parts.append("口头禅：" + "、".join(str(p) for p in card["top_phrases"][:5]))
    if card.get("sample_dialogues"):
        parts.append(f"样例对话 {len(card['sample_dialogues'])} 组")
    if card.get("source_speaker"):
        parts.append(f"源自聊天记录中的「{card['source_speaker']}」")
    return " ｜ ".join(parts)


__all__ = [
    "MAX_SAMPLE_DIALOGUES_IN_PROMPT",
    "SLIDER_HINTS",
    "SLIDER_LABELS",
    "build_greeting",
    "build_memory_block",
    "build_persona_summary_text",
    "build_system_prompt",
    "slider_labels",
]
