---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_59ebfd08cdf411f1aa22525400393706
    ReservedCode1: BV9COqAkkzTo62xv2e9Oh5Qe5LhnvRygkHrGiW9YatPWQzR5mbQbTUMm9Nzfa0sr9f1gIlF8H1Hk0WzGSW2pO0jvoNlP/Io+Q2DrFYpAoxLhX0p+Oj+WoXjsJBMBVjuPNk1i+6TZ2Ar8Pl0MdCsFlszdEiJMAk3QPGU3H9ig7mkQAldkgVsCvMDRxlI=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_59ebfd08cdf411f1aa22525400393706
    ReservedCode2: BV9COqAkkzTo62xv2e9Oh5Qe5LhnvRygkHrGiW9YatPWQzR5mbQbTUMm9Nzfa0sr9f1gIlF8H1Hk0WzGSW2pO0jvoNlP/Io+Q2DrFYpAoxLhX0p+Oj+WoXjsJBMBVjuPNk1i+6TZ2Ar8Pl0MdCsFlszdEiJMAk3QPGU3H9ig7mkQAldkgVsCvMDRxlI=
---



# 架构说明 · ARCHITECTURE

本文档说明赛博女友（cyber-girlfriend）的模块职责、数据流、记忆分层设计、LLM Provider 抽象、数据表结构与扩展点。

---

## 1. 总览

```
┌──────────────────────────────────────────────────────────────────────┐
│  浏览器（零构建 SPA：Vue 3 全局构建 + 手写 hash 路由 + fetch/SSE）      │
│  backend/static/{index.html, app.js, style.css, vendor/vue.global...} │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST(JSON) + SSE(text/event-stream)
┌───────────────────────────────▼──────────────────────────────────────┐
│  FastAPI 应用（backend/app/main.py），路由统一前缀 /api                │
│  api/: personas | cards | worldbook | import | sessions | chat         │
│        | memories | settings | feedback | backup | meta               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│  服务层 services/                                                     │
│   importer/parser   多格式聊天记录 → 统一消息结构                      │
│   importer/desensitize 统一消息结构 → 脱敏后的消息 + 命中统计           │
│   persona/extractor 消息 → 人设卡(persona_card) + 风格滑块(sliders)    │
│   persona/prompt    人设 + 状态 + 记忆 + 世界书 → system prompt / 开场白│
│   card/st_card      角色卡 V1/V2/V3 解析与导出、PNG tEXt 内嵌读写       │
│   lore/matcher      世界书关键词/常驻条目匹配 + 位置与预算控制          │
│   memory/store      记忆写入 / 打分召回 / CRUD                        │
│   memory/reflect    反思抽取记忆 + 会话摘要压缩                        │
│   chat/engine       上下文编排 + 流式生成 + mood/affection 更新        │
│   llm/*             Provider 抽象（mock / openai / ollama）           │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ SQLAlchemy 2.0 ORM
┌───────────────────────────────▼──────────────────────────────────────┐
│  SQLite：backend/data/cyber_gf.db（8 张表，启动时自动建目录、建表，     │
│  并对老库执行「查缺列 → ALTER TABLE 补列」的叠加式迁移）                │
└──────────────────────────────────────────────────────────────────────┘
```

设计原则：

1. **本地优先**：无云依赖，无遥测；除显式配置远程 Provider 外不发生任何外发请求。
2. **零配置可跑**：Provider 工厂保证任何配置缺失都能降级到 mock。
3. **零构建前端**：不引入 npm / 打包器，Vue 3 全局构建文件随仓库分发。
4. **依赖极简**：后端只用 fastapi / uvicorn / sqlalchemy / pydantic / pydantic-settings / python-multipart / httpx；中文分词用正则 + 字符 bigram 手写，不引入 jieba / numpy / 向量库。
5. **只动不删**：删除只针对数据库记录，不做文件系统批量破坏操作。

---

## 2. 模块职责

### 2.1 后端入口

| 文件 | 职责 |
| --- | --- |
| `app/main.py` | 创建 FastAPI 实例；CORS 全开；`lifespan` 中执行 `init_db()` + `seed_if_empty()`；挂载 `/api` 路由、`/static` 与 `/`（静态站点）；`GET /` 返回 `static/index.html`；`GET /health`、`GET /api/meta` |
| `app/core/config.py` | `pydantic-settings` 的 `Settings`（`env_prefix="CG_"`，`env_file=".env"`）；运行期配置读写 `get_runtime_config` / `set_runtime_config`，密钥打码 `mask_secret` |
| `app/db/base.py` | 引擎 / SessionLocal / `get_db` 依赖 / `init_db()`（建目录 + `create_all` + 调用迁移检查） |
| `app/db/migrate.py` | 轻量迁移：`PRAGMA table_info` 比对期望列，缺失则 `ALTER TABLE ADD COLUMN`（叠加式，不删列不改类型） |
| `app/db/seed.py` | 首次启动（Persona 表为空）写入 2 个示例人格：林晚（温柔知性）、阿离（傲娇毒舌） |
| `app/models/models.py` | SQLAlchemy 2.0 声明式模型（8 张表）与 JSON 字段包装方法 |
| `app/schemas/schemas.py` | Pydantic v2 请求/响应契约；常量 `SLIDER_KEYS` / `MEMORY_KINDS` / `RELATIONS` |
| `app/api/__init__.py` | 聚合 `api_router`（personas / cards / worldbook / importer / sessions / chat / memories / settings / feedback / backup），统一前缀 `/api` |

### 2.2 API 层

| 路由 | 方法 | 说明 |
| --- | --- | --- |
| `/api/personas` | GET / POST | 列表 / 创建 |
| `/api/personas/{id}` | GET / PUT / DELETE | 详情 / 更新 / 删除（级联清理会话、消息、记忆、反馈） |
| `/api/personas/generate` | POST | 入参 `import_batch_id` + `speaker`（+ 可选 name / relation / avatar_emoji / nickname_for_user），提取并保存人格 |
| `/api/personas/preview-prompt` | POST | 人设编辑页实时 system prompt 预览（不落库） |
| `/api/cards/parse` | POST | 上传 `.json` / `.png` 角色卡，解析出摘要与提示（**不落库**），供导入前确认 |
| `/api/cards/import` | POST | 角色卡 → 人格：解析 → 文本字段脱敏 → 建人格 → 内嵌 `character_book` 转世界书条目 |
| `/api/personas/{id}/card.json` | GET | 导出为角色卡 JSON（`spec=v1\|v2\|v3`） |
| `/api/personas/{id}/card.png` | GET | 导出为 PNG（`tEXt` 内嵌角色卡数据；`spec` 与 `size` 可调） |
| `/api/personas/{pid}/worldbook` | GET / POST | 该人格的世界书条目列表 / 新建条目 |
| `/api/personas/{pid}/worldbook/preview` | POST | 命中测试：给定最近对话文本，返回命中条目、注入位置与预算占用（不落库） |
| `/api/worldbook/{id}` | PUT / DELETE | 世界书条目更新 / 删除 |
| `/api/backup/export` | GET | 导出单文件 JSON 全量备份（可选是否含反馈样本、导入批次），`llm_api_key` 掩码 |
| `/api/backup/import` | POST | 导入备份：`strategy=merge_by_id\|merge_by_name\|skip_duplicates`、`dry_run` 试算、`import_api_key` 开关，返回逐表报告 |
| `/api/import/upload` | POST | multipart 上传（字段 `file`，≤24MB），自动识别格式，解析后**默认脱敏**，返回批次 id / fmt / 发言人统计 / 最近 10 条预览 / `desensitize` 统计 |
| `/api/import/batches` | GET | 批次列表；`/{id}` GET / DELETE |
| `/api/sessions` | GET / POST | 会话列表（可按 `persona_id` 过滤）/ 创建（自动写入开场白首条消息） |
| `/api/sessions/{id}` | GET / DELETE | 详情 / 删除（同时删消息） |
| `/api/sessions/{id}/messages` | GET | 消息列表（`limit` 1~1000，默认 200） |
| `/api/chat/stream` | POST | **SSE 流式对话**，事件见 §3.2 |
| `/api/memories` | GET / POST | 记忆列表（可按 `persona_id` / `kind` 过滤）/ 新增 |
| `/api/memories/{id}` | PUT / DELETE | 修改 / 删除 |
| `/api/memories/search` | POST | 检索测试：`{persona_id, query, top_k}` → `{query, count, items:[{score, memory}]}` |
| `/api/settings` | GET / PUT | 运行期配置读写（api_key 返回打码） |
| `/api/messages/{id}/feedback` | POST | 反馈：`like` / `dislike` / `rewrite`（rewrite 覆盖消息内容并写偏好样本） |
| `/api/meta`, `/health` | GET | 元信息 / 健康检查 |

### 2.3 服务层

| 模块 | 关键函数 | 职责 |
| --- | --- | --- |
| `services/importer/parser.py` | `parse_bytes(filename, raw)` | 解码（utf-8-sig/utf-8/gb18030/big5/latin-1）→ 按扩展名与内容特征识别 `wechat_txt` / `qq_txt` / `telegram_json` / `generic_json` / `csv` / `plain_txt` → 统一输出 `{fmt, messages[{speaker,content,timestamp}], speakers[{name,count}], message_count, preview}`，上限 20000 条 |
| `services/persona/extractor.py` | `extract_from_messages(messages, speaker, display_name)` | 生成 `persona_card`（nickname / top_phrases(2~4 字高频片段 Top10) / emoji_habits / punctuation_habits / avg_length / message_count / sample_dialogues 20~50 组）与 `sliders`（gentle / tsundere / sharp / clingy / proactive，0~100 启发式打分） |
| `services/persona/prompt.py` | `build_system_prompt` / `build_greeting` / `build_persona_summary_text` | 组装结构化人设提示词（人设卡 + 滑块强度 + 口癖 + 样例对话 + 心情/好感度语气调节 + 不自称 AI 等约束）；生成开场白；生成前端展示摘要 |
| `services/card/st_card.py` | `parse_card_payload` / `card_to_persona` / `card_to_worldbook_entries` / `persona_to_card` / `build_card_png` | 角色卡 V1/V2/V3 解析与规格归一；`read_png_text_chunks` / `extract_card_json_from_png` / `embed_card_json_to_png` 处理 PNG `tEXt` / `zTXt` / `iTXt` 内嵌数据（键名兼容 `chara` 与 `ccv3`）；`character_book` ↔ 世界书条目互转 |
| `services/lore/matcher.py` | `collect_hits` / `inject_into_messages` / `injection_summary` / `match_entries` | 世界书匹配：`constant` 常驻 + 关键词命中（`keys`、`case_sensitive`），按 `priority` 排序、按 `position`（`before_char` / `after_char` / `at_depth`）与字符预算裁剪，由 `chat/engine.py` 在第 3.5 步二次注入上下文，并通过 SSE `notice` 回显命中条目 |
| `services/importer/desensitize.py` | `desensitize_messages` / `desensitize_text` / `desensitize_fields` / `config_from_runtime` | 按固定顺序把手机号 / 身份证号 / 邮箱 / 银行卡 / URL / IP / QQ 替换为占位符；黑名单关键词命中则**整条丢弃**；返回脱敏结果与分类命中统计，规则由 `_RE_PHONE` / `_RE_ID_CARD` / `_RE_EMAIL` / `_RE_BANK_CARD` / `_RE_URL` / `_RE_IPV4` / `_RE_QQ` 与 `_MASKERS` 实现 |
| `services/memory/store.py` | `add_memory` / `retrieve_scored` / `retrieve` / `list_memories` / `update_memory` / `delete_memory` | 记忆 CRUD 与打分召回（公式见 §4.3），召回后更新 `last_access_at` / `access_count` |
| `services/memory/reflect.py` | `maybe_reflect(db, session)` | 每累计 `reflect_every` 条 assistant 消息触发：LLM 可用时抽取 0~3 条事实（要求 JSON 数组，解析失败容错），否则用启发式句式抽取；同时更新 `session.summary` |
| `services/chat/engine.py` | `ChatEngine.stream_reply` / `apply_feedback_to_state` / `to_sse` | 上下文编排、流式生成、边产出边落库、每轮更新 mood/affection、触发反思；`to_sse` 统一序列化 SSE 事件 |
| `services/llm/*` | 见 §5 | Provider 抽象与实现 |

---

## 3. 数据流

### 3.1 上下文编排顺序（ChatEngine）

```
[system]  人设提示词（persona/prompt.build_system_prompt）
   ├─ 人设卡：昵称、关系、对你的称呼、口癖、标点/emoji 习惯、样例对话
   ├─ 风格滑块强度描述
   └─ 当前心情 mood / 好感度 affection 对应的语气调节 + 角色约束
[system]  【长期记忆】（memory/store 召回 top_k 条，按得分降序）
[system]  【会话摘要】（session.summary）
[user/assistant] 最近 recent_window 条消息（按 id 升序）
[user]    用户当前输入
   ↓ 第 3.5 步：世界书二次注入（lore/matcher，按 position 插入到角色前 / 角色后 / 指定深度）
      · before_char → 插到消息列表最前面（system prompt 之前）
      · after_char  → 插到首条 system prompt 之后
      · at_depth    → 插到距末尾 depth 条消息之前（depth 越大越靠前）
```

### 3.2 SSE 事件格式（`media_type="text/event-stream"`）

每个事件形如 `event: <type>\ndata: <json>\n\n`：

| 事件 | 数据 | 说明 |
| --- | --- | --- |
| `delta` | `{"type":"delta","text":"..."}` | 文本块，逐块追加实现打字机效果 |
| `notice` | `{"type":"notice","level":"info","message":"..."}` | 状态提示（如降级为 mock、召回记忆） |
| `meta` | `{"type":"meta","mood":int,"affection":int}` | 会话状态更新 |
| `error` | `{"type":"error","message":"..."}` | 生成失败（异常兜底，仍以事件形式返回） |
| `done` | `{"type":"done","message_id":int,"mood":int,"affection":int,"memory_added":int}` | 本轮结束，`memory_added` 为本轮新增记忆条数 |

前端用 `fetch` + `response.body.getReader()` + `TextDecoder` 按 `\n\n` 分包解析，严格读取 `event:` / `data:` 两行。

### 3.3 一次对话的写库时机

1. 用户消息立即落库；
2. 生成过程中逐块**累积**（不逐块写库，避免碎片）；
3. 生成结束将完整 assistant 回复落库，并更新 `session.updated_at` / `mood` / `affection` / `summary`（如触发反思）。

---

## 4. 三层记忆设计

### 4.1 分层

| 层 | 载体 | 生命周期 | 作用 |
| --- | --- | --- | --- |
| L1 短期 | 最近 `recent_window` 条消息 | 单会话 | 保证语气与话题连贯 |
| L2 中期 | `chat_sessions.summary` | 随会话演进 | 压缩长对话，防止上下文爆炸 |
| L3 长期 | `memories` 表 | 跨会话持久 | 记住关于"你"的事实、偏好、事件、约定 |

### 4.2 记忆类型

| kind | 含义 | 示例 |
| --- | --- | --- |
| `fact` | 客观事实 | 用户叫小林；用户在杭州 |
| `preference` | 偏好 | 用户喜欢在深夜聊天；讨厌被催 |
| `event` | 已发生事件 | 用户下周三要面试 |
| `promise` | 约定 | 答应明天提醒用户喝水 |

### 4.3 召回打分公式

```
score = 词法相似度 × 时间衰减 × (0.5 + 0.5 × importance)

词法相似度：TF-IDF 余弦
  分词：正则 [\u4e00-\u9fa5a-zA-Z0-9]+ 提取 token
        中文 → 字符 bigram；英文/数字 → 整词
  在「查询 vs 单条记忆」之间计算 TF-IDF 向量余弦

时间衰减：0.5 ^ (距今小时数 / (30 × 24))
  即半衰期 30 天；新记忆权重高，久未访问逐渐淡化

importance：0~1，由反思阶段评估或用户手工设定
```

召回后：

- 更新 `last_access_at = now`、`access_count += 1`（被反复用到的记忆更"新"，形成正向循环）；
- 检索测试接口 `POST /api/memories/search` 使用 `touch=False`，只评分不改写访问统计。

### 4.4 反思机制（memory/reflect.py）

```
触发条件：该会话累计 assistant 消息数 % reflect_every == 0

LLM 可用：
  输入最近若干轮对话 → 要求输出 JSON 数组
  [{"content": "...", "kind": "fact|preference|event|promise", "importance": 0.7}]
  解析失败 → 容错回退到启发式

LLM 不可用（mock）：
  启发式句式命中即抽原句：
  "我叫 / 我是 / 我喜欢 / 我讨厌 / 我住在 / 我生日 / 我在做 / 我想 ..."
  importance 固定 0.6

同时更新 session.summary：
  LLM 可用 → LLM 压缩最近若干轮
  否则    → 最近若干轮拼接后截断
```

---

## 5. LLM Provider 抽象

### 5.1 接口（`services/llm/base.py`）

```python
class LLMProvider(ABC):
    async def stream(self, messages, **kwargs) -> AsyncIterator[str]: ...
    async def complete(self, messages, **kwargs) -> str: ...
```

统一消息格式：

```python
[{"role": "system" | "user" | "assistant", "content": str}, ...]
```

### 5.2 实现

| Provider | 协议 | 实现要点 |
| --- | --- | --- |
| `mock` | 无网络 | 读取 `persona_card` 的样例对话与口癖，从样例回复 / 口癖库 / 情绪模板拼装 2~4 句；`asyncio.sleep(0.03)` 逐 1~2 字产出，模拟打字机；回复随用户输入、`mood`、`affection` 变化（高黏人撒娇 / 低傲娇冷淡） |
| `openai_compat` | HTTP | `httpx.AsyncClient` POST `{base_url}/chat/completions`，`stream=True`，逐行解析 `data: ` SSE 取 `choices[0].delta.content`，遇 `[DONE]` 结束 |
| `ollama` | HTTP | POST `{base_url}/api/chat`，`stream=True`，逐行解析 JSON 取 `message.content` |

### 5.3 工厂与降级（`services/llm/factory.py`）

```
get_provider(db?) →
  provider 由运行期配置（app_configs）优先，其次代码配置
  ├─ mock   → 直接用 MockProvider
  ├─ openai → 校验 base_url 与 api_key，缺失则降级 mock
  └─ ollama → 校验 base_url，缺失则降级 mock
is_demo_mode(cfg) → 当前是否处于演示模式（前端顶部提示条依据）
reset_provider_cache() → 设置变更后清缓存，下次请求重建
```

降级时不会抛异常，而是返回 mock 并通过 SSE `notice` 事件告知前端，保证「对话永不中断」。

---

## 6. 本轮新增模块（v0.2.0）

> 本节描述 0.2.0 迭代新增的 5 个模块：`card`、`lore`、`desensitize`、`backup`、`migrate`。
> 它们均为**纯本地实现**（PNG 解析、正则匹配、JSON 序列化），不引入新的第三方依赖，不新增网络出口。

### 6.1 角色卡 `services/card/st_card.py`

| 能力 | 说明 |
| --- | --- |
| 解析 | `parse_card_payload` 接受 `.json`（V1 平铺 / V2 `data` 包裹 / V3 `spec: "chara_card_v3"`）与 `.png`（读取 `tEXt` / `zTXt` / `iTXt` 块，键名优先 `ccv3`、回退 `chara`，值可能是明文 JSON 或 base64）；`normalize_card` 统一归一为内部结构（name / description / personality / scenario / first_mes / mes_example / creator_notes / tags / alternate_greetings / character_book） |
| 转换 | `card_to_persona` 生成人格字段（`persona_card`、`sliders` 由文本启发式推断、`sample_dialogues` 由 `mes_example` 经 `<START>` 切分，上限 20 组）；`card_to_worldbook_entries` 把内嵌 `character_book` 的条目转换为世界书条目（keys / content / position / priority / constant / case_sensitive / enabled），`worldbook_entries_to_character_book` 为反向转换 |
| 导出 | `persona_to_card` 支持 `spec=v1|v2|v3`（V1 输出平铺字段，V2/V3 输出带 `data` 与 `spec` 字段的结构，避免导入方误判版本）；`build_card_png` 在没有头像时用 `make_gradient_png` 生成渐变底图，再经 `embed_card_json_to_png` 把 JSON 写入 PNG 文本块 |
| 边界 | 解析失败抛 `CardParseError`，导入前接口以 4xx 返回明确原因；`/api/cards/parse` **不落库**，只有 `/api/cards/import` 才写人格与世界书 |

导入链路：`POST /api/cards/import` → `parse_card_payload` → `normalize_card` → `desensitize_fields`（角色卡文本字段同样过脱敏规则）→ 建 Persona（`source="card_import"`，`name` 取卡内角色名）→ `card_to_worldbook_entries` 写入 `worldbook_entries`，返回 `{ok, persona, summary}`（`summary` 含 `warnings` 与脱敏统计）。
导出链路：`GET /api/personas/{id}/card.json|png` → `persona_to_card`（+ 附带的 `worldbook_entries_to_character_book`）→ 可选 `build_card_png`。

### 6.2 世界书 / Lorebook `services/lore/matcher.py` + `api/worldbook.py`

- **存储**：条目挂在 Persona 下（`worldbook_entries.persona_id`），字段为 `keys`（JSON 数组）/ `content` / `position` / `depth` / `priority` / `token_budget` / `constant` / `case_sensitive` / `enabled` / `comment` / `source`。
- **匹配**：`collect_hits` 以最近对话文本（`build_scan_text`：最近 N 条消息拼接）为 haystack，先取 `constant=true` 的常驻条目，再对启用条目做关键词命中（`case_sensitive` 未显式设置时使用全局默认）；按 `priority` 从高到低排序，累计字符数超过 `lore_budget` 后停止收录。
- **注入**：`inject_into_messages` 按 `position` 把命中块插入消息序列（返回新列表，不改入参）——`before_char` 插到列表最前面（system prompt 之前），`after_char` 插到首条 system prompt 之后，`at_depth` 插到距末尾 `depth` 条消息之前（`depth` 越大越靠前）；`render_block` 负责渲染带标题的文本块。
- **可观测**：命中结果通过 SSE `notice` 事件（`level: "lore"`，附 `items` 内容摘要与 `detail` 统计）回显，并在 `done` 事件的 `lore` 字段带上 `injection_summary`（命中键、位置分布、字符数）；`POST /api/personas/{pid}/worldbook/preview` 提供不入库的命中测试。
- **开关**：`lore_enabled`（默认开）/ `lore_budget` / `lore_scan_window`（扫描多少条历史消息）。

### 6.3 聊天记录脱敏 `services/importer/desensitize.py`

- **触发时机**：导入链路（`/api/import/upload` 与 `/api/cards/import`）在解析之后、落库之前统一调用 `desensitize_messages` / `desensitize_fields`，默认开启。
- **规则**：按固定顺序覆盖手机号（`_RE_PHONE`）、身份证号（`_RE_ID_CARD`，含 `_ID_WEIGHTS` / `_ID_CHECK_CHARS` 校验位校验）、邮箱、银行卡号（13~19 位并做边界排除）、URL、IPv4、QQ 号；命中后替换为占位符（占位符文案由 `_MASKERS` 定义）。
- **黑名单整条丢弃**：`desensitize_blacklist` 命中的消息**不进入数据库**，仅计入 `dropped` 统计（默认黑名单为空，规则可由用户在设置页维护）。
- **返回统计**：`{enabled, counts: {phone, id_card, email, bank_card, url, ipv4, qq}, counts_labeled, total_masked, dropped_messages, dropped_keywords}`，写入 `import_batches.desensitize_stats` 并随导入接口返回，前端以统计卡片展示。
- **注意**：脱敏只在**导入时**执行，命中结果不可逆；已入库的历史数据不会被回溯处理。

### 6.4 全量备份导入导出 `api/backup.py`

| 方向 | 行为 |
| --- | --- |
| 导出 `GET /api/backup/export` | 输出单文件 JSON：`format` / `format_version=1` / `exported_at` / `counts` / `settings` + 按人格**嵌套**的数据（`personas[].worldbook` / `.memories` / `.sessions[].messages`）；`include_feedback=true`（默认）携带反馈样本，`include_import_batches=false`（默认）不携带导入批次（体积大）；`download=false` 时直接返回 JSON 不触发下载 |
| 密钥处理 | `settings.llm_api_key` 一律经 `mask_secret` 打码，另给 `llm_api_key_set` 布尔标记；导出文件里不含明文密钥 |
| 导入 `POST /api/backup/import` | multipart 上传（≤64MB，`format` 不匹配或缺少 `personas` 直接 4xx）；`strategy=merge_by_id`（默认）/ `merge_by_name` / `skip_duplicates`；`dry_run=true` 只试算并 `rollback`；`import_api_key=false`（默认）忽略备份中的密钥，避免把掩码串写回库 |
| 返回报告 | `{ok, strategy, dry_run, created, skipped, remapped, warnings, counts}`；id 冲突时重映射外键并把重编号数量写入 `remapped` / `warnings` |
| 局限 | 只覆盖**业务数据**，不含 `backend/data/` 下的上传原件与 `.env`；恢复后需重新配置 Provider 密钥 |

### 6.5 轻量迁移 `app/db/migrate.py`

- 启动时由 `init_db()` 调用：对每张表执行 `PRAGMA table_info`，与模型声明的列集合比对，**缺失列**执行 `ALTER TABLE ... ADD COLUMN` 补齐。
- 只做**叠加式**变更：不删列、不改类型、不做数据回填；因此升级无需手工 SQL，也不会破坏老库。
- 适用于 SQLite 单文件库的轻量场景；若未来引入更复杂的结构变更（改类型 / 拆表 / 大数据回填），应改用 Alembic 等正式迁移框架（Roadmap）。

## 7. 数据表说明

数据库：`backend/data/cyber_gf.db`（SQLite，启动时自动创建目录与表；不使用 Alembic）。

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `personas` | `id, name, avatar_emoji, relation, nickname_for_user, persona_card(JSON文本), sliders(JSON文本), greeting, source, creator_notes, tags(JSON), character_version, card_spec, extensions(JSON), created_at` | 人格；`source ∈ {manual, imported, card_import, backup}`；`creator_notes` / `tags` / `character_version` / `card_spec` / `extensions` 五个字段用于角色卡往返导出（`card_spec` 记录来源规格，V1 卡导入时可为空） |
| `worldbook_entries` | `id, persona_id, keys(JSON), content, enabled, constant, case_sensitive, priority, position, depth, token_budget, comment, source, created_at` | 世界书条目；`position ∈ {before_char, after_char, at_depth}`（`depth` 仅 `at_depth` 生效），`token_budget=0` 表示不限，`source ∈ {manual, card_import, backup}` |
| `chat_sessions` | `id, persona_id, title, mood(0-100), affection(0-100), summary, created_at, updated_at` | 会话；`mood` / `affection` 驱动语气 |
| `messages` | `id, session_id, role, content, created_at, feedback(0/1/-1), rewritten` | 消息；`feedback` 记录点赞/踩，`rewritten` 标记被用户改写 |
| `memories` | `id, persona_id, session_id(可空), content, kind, importance(0-1), source, created_at, last_access_at, access_count` | 长期记忆；`kind ∈ {fact, preference, event, promise}` |
| `feedbacks` | `id, message_id, session_id, persona_id, action, original, revised, created_at` | 反馈样本；rewrite 时存「原回复 → 期望回复」 |
| `import_batches` | `id, filename, fmt, message_count, speakers(JSON), preview(JSON), payload(JSON), desensitize_enabled, desensitize_stats(JSON), created_at` | 导入批次**脱敏后**的解析结果，供人格生成复用；`payload` 存全量消息，`desensitize_stats` 存各类命中次数 |
| `app_configs` | `key, value, updated_at` | 运行期配置键值对，优先级高于 `.env` 与默认值 |

索引建议（模型内已按需声明）：`messages.session_id`、`memories.persona_id`、`chat_sessions.persona_id`、`worldbook_entries.persona_id`。

---

## 8. 扩展点

| 想做的事 | 建议改哪里 |
| --- | --- |
| 支持新的聊天记录格式 | 在 `services/importer/parser.py` 增加识别分支，返回统一结构即可，API 与前端无需改动 |
| 支持新的角色卡规格 | 在 `services/card/st_card.py` 的 `normalize_card` 增加字段归一并补 `persona_to_card` 的导出分支；`card_spec` 需同步扩枚举 |
| 扩充脱敏规则 | 在 `services/importer/desensitize.py` 增加 `_RE_*` 正则与 `_MASKERS` 占位符，并在 `CATEGORY_LABELS` 补中文标签（前端统计直接读取该映射） |
| 换向量检索 / 语义召回 | 实现 `services/memory/store.py` 中 `retrieve_scored` 的同签名函数（关键词 → 向量相似度），保持返回 `[(memory, score)]` |
| 接入新的模型服务 | 继承 `services/llm/base.py` 的 `LLMProvider`，在 `factory.py` 中注册分支（如 Anthropic / Gemini / vLLM） |
| 人设维度扩展 | 同步修改 `SLIDER_KEYS`（schemas）与 `prompt.py` 的强度描述、前端滑块数组 |
| 更强的提示词 / 防出戏 | 集中修改 `services/persona/prompt.py::build_system_prompt` |
| 偏好学习落地 | 读取 `feedbacks` 表（尤其 `action='rewrite'` 的 original/revised 对），在生成前追加少样本示例 |
| 主动问候 / 纪念日 | 新增定时任务模块，读取 `kind` 为 `promise` / `event` 的记忆，调用 `chat/engine` 生成主动消息 |

---

## 9. 已知约束

- SQLite 单文件；表结构变更走 `app/db/migrate.py` 的**叠加式**补列（只加列，不删列 / 不改类型 / 不回填）。若需改类型或拆表，仍需手动处理或删除 `backend/data/cyber_gf.db` 重建。
- 记忆检索为纯词法（TF-IDF + bigram），不含语义向量能力，同义改写召回有限（依赖 P1 路线图）。
- 世界书匹配为关键词子串匹配，不做语义 / 向量召回；`token_budget` 按字符数近似估算，与真实 tokenizer 存在偏差。
- 脱敏为**正则规则**实现，仅覆盖常见结构化标识（手机号 / 证件号 / 邮箱 / 银行卡 / URL / IP / QQ），无法识别姓名、地址等非结构化隐私；导入时执行且不可逆，不回溯处理已入库数据。
- 备份导入在 id 冲突时重编号并同步重映射外键，`remapped` 仅作提示，没有人工核对界面。
- 前端为演示级 SPA：单文件、手写 hash 路由，未做组件级拆分与状态持久化（刷新即重载）。
- LLM 反思抽取在 mock 模式下走启发式规则，抽取覆盖率低于真实模型。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
