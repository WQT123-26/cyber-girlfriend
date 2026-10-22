"""Pydantic v2 数据契约（请求 / 响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

SLIDER_KEYS = ["gentle", "tsundere", "sharp", "clingy", "proactive"]
MEMORY_KINDS = ["fact", "preference", "event", "promise"]
RELATIONS = ["女友", "老婆", "闺蜜", "自定义"]


# --------------------------------------------------------------------------
# 人格
# --------------------------------------------------------------------------
class PersonaBase(BaseModel):
    name: str = Field(default="未命名", max_length=64)
    avatar_emoji: str = Field(default="🌸", max_length=16)
    relation: str = Field(default="女友", max_length=32)
    nickname_for_user: str = Field(default="你", max_length=64)
    sliders: Dict[str, int] = Field(default_factory=dict)
    persona_card: Dict[str, Any] = Field(default_factory=dict)
    greeting: str = ""
    # ---- 角色卡（SillyTavern Character Card）元信息 ----
    creator_notes: str = ""
    tags: List[str] = Field(default_factory=list)
    character_version: str = ""
    card_spec: str = ""


class PersonaCreate(PersonaBase):
    source: str = "manual"


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    avatar_emoji: Optional[str] = None
    relation: Optional[str] = None
    nickname_for_user: Optional[str] = None
    sliders: Optional[Dict[str, int]] = None
    persona_card: Optional[Dict[str, Any]] = None
    greeting: Optional[str] = None
    creator_notes: Optional[str] = None
    tags: Optional[List[str]] = None
    character_version: Optional[str] = None
    card_spec: Optional[str] = None


class PersonaOut(PersonaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str = "manual"
    created_at: Optional[datetime] = None
    summary_text: str = ""


class PromptPreviewIn(BaseModel):
    """人设编辑页右侧「实时预览 system prompt」。"""

    persona: PersonaCreate
    sample_user_message: str = "在吗？"


class PromptPreviewOut(BaseModel):
    system_prompt: str
    greeting: str
    summary_text: str


class GeneratePersonaIn(BaseModel):
    import_batch_id: int
    speaker: str
    name: Optional[str] = None
    relation: str = "女友"
    avatar_emoji: str = "💫"
    nickname_for_user: str = "你"


# --------------------------------------------------------------------------
# 会话与消息
# --------------------------------------------------------------------------
class SessionCreate(BaseModel):
    persona_id: int
    title: Optional[str] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    persona_name: str = ""
    persona_emoji: str = "🌙"
    title: str
    mood: int
    affection: int
    summary: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_message: str = ""
    message_count: int = 0


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    created_at: Optional[datetime] = None
    feedback: int = 0
    rewritten: bool = False


class ChatRequest(BaseModel):
    session_id: int
    content: str
    use_memory: bool = True


# --------------------------------------------------------------------------
# 记忆
# --------------------------------------------------------------------------
class MemoryCreate(BaseModel):
    persona_id: int
    session_id: Optional[int] = None
    content: str
    kind: str = "fact"
    importance: float = 0.6
    source: str = "manual"


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    kind: Optional[str] = None
    importance: Optional[float] = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    session_id: Optional[int] = None
    content: str
    kind: str
    importance: float
    source: str
    created_at: Optional[datetime] = None
    last_access_at: Optional[datetime] = None
    access_count: int = 0
    score: Optional[float] = None


class MemorySearchIn(BaseModel):
    persona_id: int
    query: str
    top_k: int = 5


class MemorySearchItem(BaseModel):
    score: float
    memory: MemoryOut


class MemorySearchOut(BaseModel):
    query: str
    persona_id: int
    count: int = 0
    items: List[MemorySearchItem] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 导入
# --------------------------------------------------------------------------
class SpeakerStat(BaseModel):
    name: str
    count: int


class ImportPreviewItem(BaseModel):
    speaker: str
    content: str
    timestamp: Optional[str] = None


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    fmt: str
    message_count: int
    speakers: List[SpeakerStat] = Field(default_factory=list)
    preview: List[ImportPreviewItem] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    # ---- 脱敏（隐私处理）结果 ----
    desensitize_enabled: bool = True
    desensitize: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# 设置
# --------------------------------------------------------------------------
class SettingsOut(BaseModel):
    llm_provider: str
    llm_base_url: str
    llm_api_key_masked: str
    llm_api_key_set: bool
    llm_model: str
    llm_temperature: float
    memory_top_k: int
    recent_window: int
    reflect_every: int
    demo_mode: bool
    provider_options: List[str] = ["mock", "openai", "ollama"]
    # ---- 世界书注入 ----
    lore_enabled: bool = True
    lore_budget: int = 1200
    lore_scan_window: int = 12
    # ---- 导入脱敏 ----
    desensitize_enabled: bool = True
    desensitize_blacklist: str = ""
    desensitize_rules: List[Dict[str, str]] = Field(default_factory=list)  # 规则清单（key/label/placeholder）


class SettingsUpdate(BaseModel):
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    memory_top_k: Optional[int] = None
    recent_window: Optional[int] = None
    reflect_every: Optional[int] = None
    lore_enabled: Optional[bool] = None
    lore_budget: Optional[int] = None
    lore_scan_window: Optional[int] = None
    desensitize_enabled: Optional[bool] = None
    desensitize_blacklist: Optional[str] = None


# --------------------------------------------------------------------------
# 反馈
# --------------------------------------------------------------------------
class FeedbackIn(BaseModel):
    action: str  # like | dislike | rewrite
    content: Optional[str] = None  # rewrite 时必填


class FeedbackOut(BaseModel):
    ok: bool = True
    message_id: int
    feedback: int = 0
    content: str = ""
    action: str = ""
    rewritten: bool = False
    mood: int = 0
    affection: int = 0


# --------------------------------------------------------------------------
# 世界书 / Lorebook
# --------------------------------------------------------------------------
WORLDBOOK_POSITIONS: List[str] = ["before_char", "after_char", "at_depth"]


class WorldBookEntryIn(BaseModel):
    """新建世界书条目。``keys`` 为空则建议配合 ``constant=True`` 常驻注入。"""

    keys: List[str] = Field(default_factory=list)
    content: str = ""
    enabled: bool = True
    constant: bool = False
    case_sensitive: bool = False
    priority: int = 100
    position: str = "before_char"
    depth: int = 4
    token_budget: int = 0
    comment: str = ""


class WorldBookEntryUpdate(BaseModel):
    keys: Optional[List[str]] = None
    content: Optional[str] = None
    enabled: Optional[bool] = None
    constant: Optional[bool] = None
    case_sensitive: Optional[bool] = None
    priority: Optional[int] = None
    position: Optional[str] = None
    depth: Optional[int] = None
    token_budget: Optional[int] = None
    comment: Optional[str] = None


class WorldBookEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    keys: List[str] = Field(default_factory=list)
    content: str = ""
    enabled: bool = True
    constant: bool = False
    case_sensitive: bool = False
    priority: int = 100
    position: str = "before_char"
    depth: int = 4
    token_budget: int = 0
    comment: str = ""
    source: str = "manual"
    created_at: Optional[datetime] = None


class WorldBookListOut(BaseModel):
    persona_id: int
    count: int = 0
    entries: List[WorldBookEntryOut] = Field(default_factory=list)


class WorldBookPreviewOut(BaseModel):
    """调试用：给定一段文本，看哪些条目会被命中。"""

    persona_id: int
    scan_text: str = ""
    count: int = 0
    stats: Dict[str, Any] = Field(default_factory=dict)
    items: List[Dict[str, Any]] = Field(default_factory=list)


class WorldBookPreviewIn(BaseModel):
    text: str = ""
    token_budget: Optional[int] = None


# --------------------------------------------------------------------------
# 角色卡（SillyTavern Character Card）导入 / 导出
# --------------------------------------------------------------------------
class CardImportSummary(BaseModel):
    """角色卡解析摘要（供前端展示「字段命中情况 + 警告」）。"""

    source_format: str = ""  # json | png
    spec: str = ""  # chara_card_v2 | chara_card_v3 | v1
    spec_version: str = ""
    png_keyword: str = ""
    fields_hit: List[str] = Field(default_factory=list)
    fields_missing: List[str] = Field(default_factory=list)
    greeting_length: int = 0
    sample_dialogue_count: int = 0
    alternate_greeting_count: int = 0
    worldbook_entry_count: int = 0
    worldbook_saved: int = 0
    warnings: List[str] = Field(default_factory=list)
    desensitize_enabled: bool = True
    desensitize: Dict[str, Any] = Field(default_factory=dict)


class CardImportOut(BaseModel):
    ok: bool = True
    persona: PersonaOut
    summary: CardImportSummary


# --------------------------------------------------------------------------
# 全量备份
# --------------------------------------------------------------------------
class BackupImportOut(BaseModel):
    ok: bool = True
    strategy: str = "by_id"
    created: Dict[str, int] = Field(default_factory=dict)
    skipped: Dict[str, int] = Field(default_factory=dict)
    remapped: Dict[str, int] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
