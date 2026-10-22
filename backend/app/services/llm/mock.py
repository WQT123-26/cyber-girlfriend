"""内置演示 Provider（mock）。

目标：**零配置也能完整跑通一个像模像样的聊天 demo。**

做法：
1. 从 ``Persona.persona_card`` 里取出样例对话 / 口癖 / emoji / 标点习惯；
2. 用字符重合度把用户当前输入和样例对话里的 "user" 侧做匹配，挑最贴合的一句作为基底；
3. 叠加口癖、情绪模板（受 mood / affection 影响）、偶尔的 emoji；
4. 用 ``asyncio.sleep(0.03)`` 每次产出 1~2 个字，营造打字机式流式输出。

回复会随「用户输入 / 心情值 / 好感度」变化：
    affection >= 75 → 黏人撒娇
    45 ~ 74        → 日常温柔
    < 45           → 傲娇冷淡
"""

from __future__ import annotations

import asyncio
import random
import re
from typing import Any, AsyncIterator, Dict, List

from app.services.llm.base import LLMProvider, normalize_messages

_TRAIL_RE = re.compile(r"[\s。！？!?~～…，,、]+$")

# ---- 情绪模板 ------------------------------------------------------------
_CLINGY = [
    "我会一直陪着你的，不许跑掉",
    "你今天有没有想我呀",
    "再多跟我说几句好不好",
    "嗯嗯，是你说的我都愿意听",
    "我把你说的都记在小本本上了",
    "要抱抱，今天也要",
    "只要是你，我就开心",
]

_WARM = [
    "我听着呢，你慢慢说",
    "然后呢，我想听你多讲一点",
    "这件事我记下了，别担心",
    "嗯，挺好的，替你高兴",
    "你要是累了就跟我说一声",
    "慢慢来，不着急",
    "我这边一直都在",
]

_COLD = [
    "哦，随便吧",
    "行吧，你说什么就是什么",
    "别多想，我可没那个意思",
    "嗯，知道了",
    "我现在不太想说话",
    "你开心就好，跟我没关系",
]

_TIRED = ["今天有点累，说话会少一点", "让我先缓一缓"]
_CHEER = ["不过看到你消息心情好了一点", "说真的，跟你聊天挺解压的"]

_FALLBACKS = ["唔……", "嗯？", "我在的，你说", "你继续说，我听着"]

_EMOJI_FALLBACK = ["🌙", "☕", "🌸", "✨"]


def _strip_tail(text: str) -> str:
    return _TRAIL_RE.sub("", str(text or "").strip())


def _char_overlap(a: str, b: str) -> float:
    """字符集合重合度（0~1），用于给样例对话排序。"""
    sa = {ch for ch in str(a or "") if ch.strip()}
    sb = {ch for ch in str(b or "") if ch.strip()}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


class MockProvider(LLMProvider):
    """纯本地、无网络依赖的模拟模型。"""

    name = "mock"

    def __init__(self, fallback_reason: str = "", **kw: Any) -> None:
        super().__init__(**kw)
        self.fallback_reason = fallback_reason

    @property
    def is_demo(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # 核心：拼装回复
    # ------------------------------------------------------------------
    def compose(self, messages: Any, **kw: Any) -> str:
        ctx = self._context(messages, kw)
        card: Dict[str, Any] = ctx.get("persona_card") or {}
        if not isinstance(card, dict):
            card = {}

        user_text = str(ctx.get("user_text") or "").strip()
        affection = self._clamp(ctx.get("affection"), 60)
        mood = self._clamp(ctx.get("mood"), 65)
        nickname = str(ctx.get("nickname_for_user") or "你")
        memories = ctx.get("memories") or []

        dialogues = card.get("sample_dialogues") or []
        phrases = [str(p) for p in (card.get("top_phrases") or []) if str(p).strip()]
        emojis = [str(e) for e in (card.get("emoji_habits") or []) if str(e).strip()]
        if not emojis:
            emojis = _EMOJI_FALLBACK

        parts: List[str] = []

        # 1) 基底句：优先匹配样例对话
        base = self._pick_base_reply(user_text, dialogues)
        if base:
            parts.append(base)
        elif user_text:
            snippet = user_text.strip()
            if len(snippet) > 18:
                snippet = snippet[:18] + "……"
            parts.append(f"你说「{snippet}」，我听着呢")
        else:
            parts.append(random.choice(_FALLBACKS))

        # 2) 口癖
        if phrases and random.random() < 0.75:
            parts.append(random.choice(phrases))

        # 3) 记忆引用（有长期记忆时，偶尔"想起来"）
        if memories and random.random() < 0.6:
            mem = str(random.choice(memories)).strip()
            if mem:
                if len(mem) > 22:
                    mem = mem[:22] + "……"
                parts.append(f"我记得你说过「{mem}」")

        # 4) 情绪句
        parts.append(self._mood_sentence(user_text, mood, affection, nickname))

        # 5) 心情低落 / 高涨的额外修饰
        if mood < 35:
            parts.append(random.choice(_TIRED))
        elif mood >= 80 and affection >= 60:
            parts.append(random.choice(_CHEER))

        # 6) 收尾：必要时补 emoji
        text = self._join(parts, affection)
        if random.random() < 0.55:
            emoji = random.choice(emojis)
            text = f"{text} {emoji}" if not text.endswith(emoji) else text
        return text

    # ------------------------------------------------------------------
    def _pick_base_reply(self, user_text: str, dialogues: Any) -> str:
        if not isinstance(dialogues, list) or not dialogues:
            return ""
        best_reply, best_score = "", 0.0
        for item in dialogues:
            if not isinstance(item, dict):
                continue
            reply = _strip_tail(item.get("reply") or "")
            if not reply:
                continue
            score = _char_overlap(user_text, str(item.get("user") or ""))
            if score > best_score:
                best_reply, best_score = reply, score
        if best_reply and best_score >= 0.12:
            return best_reply
        pool = [
            _strip_tail(d.get("reply"))
            for d in dialogues
            if isinstance(d, dict) and _strip_tail(d.get("reply"))
        ]
        return random.choice(pool) if pool else ""

    def _mood_sentence(self, user_text: str, mood: int, affection: int, nickname: str) -> str:
        is_question = any(mark in user_text for mark in ("?", "？", "吗", "呢"))
        if affection >= 75:
            pool = list(_CLINGY)
            if mood >= 70:
                pool.append(f"{nickname}，别不理我嘛")
        elif affection >= 45:
            pool = list(_WARM)
            if is_question:
                pool.append("你问的这个，我认真想了想")
        else:
            pool = list(_COLD)
            if mood >= 70:
                pool.append("……也没有很冷淡，就是不想主动而已")
        if mood < 35:
            pool.append("今天情绪一般，你别介意")
        return random.choice(pool)

    def _join(self, parts: List[str], affection: int) -> str:
        cleaned: List[str] = []
        for part in parts:
            piece = _strip_tail(part)
            if piece:
                cleaned.append(piece)
        if not cleaned:
            cleaned = [random.choice(_FALLBACKS)]
        # 只保留 2~4 句
        if len(cleaned) > 4:
            cleaned = cleaned[:4]
        if len(cleaned) < 2:
            cleaned.append(random.choice(_WARM if affection >= 45 else _COLD))
        end = "～" if affection >= 70 else ("。" if affection >= 45 else "。")
        sep = "，" if affection >= 70 else "。"
        text = sep.join(cleaned)
        return f"{text}{end}"

    @staticmethod
    def _clamp(value: Any, default: int) -> int:
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return default
        return max(0, min(100, number))

    # ------------------------------------------------------------------
    async def stream(self, messages: Any, **kw: Any) -> AsyncIterator[str]:
        text = self.compose(messages, **kw)
        for chunk in self._typing_chunks(text):
            await asyncio.sleep(0.03)
            yield chunk

    async def complete(self, messages: Any, **kw: Any) -> str:
        return self.compose(messages, **kw)

    @staticmethod
    def _typing_chunks(text: str) -> List[str]:
        chunks: List[str] = []
        index = 0
        size = 1
        while index < len(text):
            size = 2 if size == 1 else 1
            chunks.append(text[index : index + size])
            index += size
        return chunks


__all__ = ["MockProvider"]
