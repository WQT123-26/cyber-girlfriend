"""数据库模型（SQLAlchemy 2.0 声明式风格）。

共 8 张表：
    personas          人格
    worldbook_entries 世界书条目（挂在人格下）
    chat_sessions     会话
    messages          消息
    memories          长期记忆
    feedbacks         反馈样本（偏好数据）
    import_batches    导入批次
    app_configs       运行期配置覆盖
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now()


def _loads(text: Optional[str], fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return fallback
    return value


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({}, ensure_ascii=False)


class Persona(Base):
    """AI 人格。"""

    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), default="未命名", nullable=False)
    avatar_emoji: Mapped[str] = mapped_column(String(16), default="🌸", nullable=False)
    relation: Mapped[str] = mapped_column(String(32), default="女友", nullable=False)
    nickname_for_user: Mapped[str] = mapped_column(String(64), default="你", nullable=False)
    persona_card: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    sliders: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    greeting: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    # ---- 角色卡（SillyTavern Character Card）元信息 ----
    creator_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON 列表
    character_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    card_spec: Mapped[str] = mapped_column(String(32), default="", nullable=False)  # v1 / chara_card_v2 / chara_card_v3
    extensions: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON 对象（原样回存，保证导出可逆）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    # ---- 便捷访问器：对外统一暴露 dict，内部仍是 JSON 文本 ----
    def tag_list(self) -> list:
        value = _loads(self.tags, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def set_tag_list(self, value) -> None:
        self.tags = _dumps([str(item) for item in (value or []) if str(item).strip()])

    def extension_dict(self) -> Dict[str, Any]:
        value = _loads(self.extensions, {})
        return value if isinstance(value, dict) else {}

    def set_extensions(self, value: Dict[str, Any]) -> None:
        self.extensions = _dumps(value or {})

    def card(self) -> Dict[str, Any]:
        value = _loads(self.persona_card, {})
        return value if isinstance(value, dict) else {}

    def set_card(self, value: Dict[str, Any]) -> None:
        self.persona_card = _dumps(value or {})

    def slider_dict(self) -> Dict[str, int]:
        value = _loads(self.sliders, {})
        if not isinstance(value, dict):
            return {}
        result: Dict[str, int] = {}
        for key, raw in value.items():
            try:
                result[key] = int(float(raw))
            except (TypeError, ValueError):
                continue
        return result

    def set_sliders(self, value: Dict[str, Any]) -> None:
        self.sliders = _dumps(value or {})


class WorldBookEntry(Base):
    """世界书 / Lorebook 条目（挂在 Persona 下）。

    注入规则见 ``app.services.lore.matcher``：
        * ``constant=True``  —— 常驻条目，每轮恒注入
        * 其余条目按 ``keys`` 命中最近 N 轮对话文本触发
        * ``position`` 决定插入位置：before_char / after_char / at_depth
        * ``token_budget`` 为 0 表示不限；预算统一用字符数近似 token
    """

    __tablename__ = "worldbook_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("personas.id"), index=True, nullable=False)
    keys: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON 列表
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    constant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # 越大越先注入
    position: Mapped[str] = mapped_column(String(16), default="before_char", nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=4, nullable=False)  # 仅 at_depth 生效
    token_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = 不限
    comment: Mapped[str] = mapped_column(String(128), default="", nullable=False)  # 条目备注 / 名称
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)  # manual | card_import | backup
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    def key_list(self) -> list:
        value = _loads(self.keys, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def set_key_list(self, value) -> None:
        self.keys = _dumps([str(item) for item in (value or []) if str(item).strip()])


class ChatSession(Base):
    """一次连续聊天会话。"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("personas.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), default="新的对话", nullable=False)
    mood: Mapped[int] = mapped_column(Integer, default=65, nullable=False)
    affection: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)


class Message(Base):
    """聊天消息。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    feedback: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 / 1(赞) / -1(踩)
    rewritten: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Memory(Base):
    """长期记忆条目。"""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("personas.id"), index=True, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="fact", nullable=False)  # fact|preference|event|promise
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="reflect", nullable=False)  # reflect|manual|import
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    last_access_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Feedback(Base):
    """用户反馈样本（点赞 / 点踩 / 改写）。"""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    persona_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16), default="like", nullable=False)  # like|dislike|rewrite
    original: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revised: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class ImportBatch(Base):
    """一次聊天记录导入批次。"""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    fmt: Mapped[str] = mapped_column(String(32), default="plain_txt", nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speakers: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON
    preview: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON（最近 10 条）
    payload: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON（全量消息，供人格提取）
    desensitize_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    desensitize_stats: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON（各类命中次数）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    def speaker_list(self):
        value = _loads(self.speakers, [])
        return value if isinstance(value, list) else []

    def preview_list(self):
        value = _loads(self.preview, [])
        return value if isinstance(value, list) else []

    def message_list(self):
        value = _loads(self.payload, [])
        return value if isinstance(value, list) else []

    def set_speaker_list(self, value) -> None:
        self.speakers = _dumps(list(value or []))

    def set_preview_list(self, value) -> None:
        self.preview = _dumps(list(value or []))

    def set_message_list(self, value) -> None:
        self.payload = _dumps(list(value or []))

    def stats_dict(self) -> Dict[str, Any]:
        value = _loads(self.desensitize_stats, {})
        return value if isinstance(value, dict) else {}

    def set_stats_dict(self, value: Dict[str, Any]) -> None:
        self.desensitize_stats = _dumps(value or {})


class AppConfig(Base):
    """运行期配置覆盖（DB 值优先于 .env 默认值）。"""

    __tablename__ = "app_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)


__all__ = [
    "AppConfig",
    "ChatSession",
    "Feedback",
    "ImportBatch",
    "Memory",
    "Message",
    "Persona",
    "WorldBookEntry",
]
