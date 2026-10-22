---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_50d5fc98cdf411f1aa22525400393706
    ReservedCode1: EanLMEo4TdMrKl7Gdt2fFKdKO9ubYSmyVn6XXlZJbpSPMosIK0Q4ATthXkadQ4QHm8ZEbUegIJnhbvQ3l+OKpE0Os1qgco4xfryAatMfQeAgY7xmXTf3k1HSPUplq503ryrnwPtcHD3bEqug64u21JKRTBBvaFo8/10YSM2PtELeu6pqHk4FsUIkQNE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_50d5fc98cdf411f1aa22525400393706
    ReservedCode2: EanLMEo4TdMrKl7Gdt2fFKdKO9ubYSmyVn6XXlZJbpSPMosIK0Q4ATthXkadQ4QHm8ZEbUegIJnhbvQ3l+OKpE0Os1qgco4xfryAatMfQeAgY7xmXTf3k1HSPUplq503ryrnwPtcHD3bEqug64u21JKRTBBvaFo8/10YSM2PtELeu6pqHk4FsUIkQNE=
---



# 赛博女友 / cyber-girlfriend

> **中文一句话定位**：把你的聊天记录变成一位「记得你」的本地 AI 聊天搭子——本地优先、零构建前端、默认不配任何 API Key 也能完整跑通。
>
> **English one-liner**：A local-first AI companion that turns your exported chat history into a persona with long-term memory — zero-build frontend, SQLite storage, and a mock provider so it runs without any API key.

- 技术栈：**Python 3.11+ / FastAPI + SQLAlchemy 2.0 + SQLite**，前端为 **Vue 3 全局构建的单页应用（无 npm、无打包、无 CDN）**。
- 当前版本：`0.2.0`（详见 [CHANGELOG.md](CHANGELOG.md)）。
- 许可证：MIT。数据默认只落在本机，卸载即删。

---

## 目录

**中文**

- [与同类项目的差异](#与同类项目的差异)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [API 概览](#api-概览)
- [配置项](#配置项)
- [隐私与数据安全](#隐私与数据安全)
- [路线图](#路线图)
- [参与贡献](#参与贡献)
- [许可证与免责声明](#许可证与免责声明)

**English**

- [English Overview](#english-overview)
- [Comparison](#comparison)
- [Features](#features)
- [Quick Start](#quick-start)
- [Privacy & Data Safety](#privacy--data-safety)
- [Roadmap](#roadmap)
- [License](#license)

---

## 与同类项目的差异

同类项目各有侧重，下表只对比**能力取向**，不构成优劣评价（信息基于各自公开文档，可能随版本变化）：

| 维度 | 赛博女友 cyber-girlfriend | SillyTavern | WeClone | Open-LLM-VTuber |
| --- | --- | --- | --- | --- |
| 核心定位 | 本地优先的「聊天记录 → 人格 → 长期陪伴」完整小应用 | 面向角色扮演的 LLM 前端 / 客户端 | 用微信聊天记录微调「数字分身」模型 | 带 Live2D 形象的语音实时对话客户端 |
| 运行形态 | Python 单进程 + SQLite + 静态 SPA，一条命令启动 | Node 前端，需自行外接推理后端 | 需 GPU 完成训练，产出模型权重 | 需 LLM + ASR + TTS 多组件协同 |
| 从聊天记录提取人设 | ✅ 内置（微信 / QQ / Telegram / CSV / 裸文本） | ❌ 主要靠手写或导入角色卡 | ✅ 作为训练语料（非人设卡） | ❌ |
| 酒馆角色卡（V1/V2/V3，含 PNG 内嵌） | ✅ 导入 + 导出（JSON / PNG） | ✅ 原生支持，生态最丰富 | ❌ | 部分支持（依赖角色卡插件） |
| 世界书 / Lorebook | ✅ 关键词 + 常驻条目，支持 position / depth / 预算 | ✅ World Info，功能更完备 | ❌ | ❌ |
| 长期记忆 | ✅ 三层（窗口 / 摘要 / 长期），自动反思，无需额外组件 | 需安装扩展（如 Vector Storage / Summarize） | 体现在模型权重中 | 依赖所接 LLM 的上下文 |
| 语音 / 虚拟形象 | ⛔ 未实现（Roadmap P2） | 需扩展（TTS、表情插件） | ⛔ | ✅ 语音实时对话 + Live2D |
| 反馈学习 | ✅ 点赞 / 踩 / 改写样本落库，影响语气 | 部分（依赖扩展） | 需重新训练 | ❌ |
| 部署门槛 | 低：`pip install` 即用；或 Docker 一条命令 | 中：需 Node + 后端服务 | 高：GPU + 训练流程 | 中高：多模型与音频链路 |
| 数据位置 | 完全本地 SQLite，可整体备份 / 迁移 | 本地 + 你所配置的后端 | 本地训练数据与权重 | 本地 / 远程混合 |

**一句话取舍**：如果你想要「开箱即用的角色卡生态」，选 SillyTavern；想要「用自己语气说话的数字分身」，选 WeClone；想要「能语音对话的虚拟形象」，选 Open-LLM-VTuber。本项目补的是另一块：**把真实聊天记录沉淀成可信的人设与长期记忆，并且整套东西足够轻、数据完全留在本地**。

---

## 功能特性

### 人格与角色卡（已实现）

- **聊天记录导入**：自动识别微信 PC 端 txt、QQ 消息管理器 txt、Telegram Desktop json、通用 json / csv 与「昵称: 内容」纯文本，无需手动选格式；自动统计发言人并生成预览（单文件上限 24MB）。
- **人设自动提取**：从指定发言人的历史消息中提取高频口癖、emoji 与标点习惯、平均句长、真实样例对话，并启发式给出 5 维风格滑块（温柔 / 傲娇 / 毒舌 / 黏人 / 主动）。
- **手动捏人**：名称、头像 emoji、关系、对你的称呼、风格滑块、开场白、补充描述均可编辑。
- **酒馆角色卡互通**：导入 `.json` / `.png`（解析 PNG 的 `tEXt` / `zTXt` / `iTXt` 内嵌数据，兼容 `chara` 与 `ccv3`），支持 V1 / V2 / V3；也可把本机人格导出为对应规格的 JSON 或 PNG。角色卡内嵌的 `character_book` 会转成该人格的世界书条目。
- **世界书 / Lorebook**：常驻条目与关键词触发两种模式，支持优先级排序、大小写敏感、注入位置（角色前 / 角色后 / 指定深度）与字符预算；提供「命中测试」预览，调整后可即时验证。

### 对话与记忆（已实现）

- **SSE 流式回复**：逐字打字机效果，可随时停止生成。
- **三层记忆**：最近对话窗口 + 会话摘要 + 长期记忆；召回打分 = 词法相似度 × 时间衰减 × 重要度。
- **自动反思**：每累计 N 条 AI 回复触发一次，抽取事实 / 偏好 / 事件 / 约定写入长期记忆，并压缩会话摘要。
- **情绪与好感**：按关键词、长度与反馈规则式更新，影响语气。
- **反馈闭环**：点赞 / 点踩微调情绪；改写会覆盖该条回复并作为偏好样本落库。
- **消息操作**：重新生成、复制、编辑后重发；内容按 Markdown 渲染（先转义再替换，防 XSS）。

### 隐私与数据（已实现）

- **导入脱敏**：默认开启，自动替换手机号、身份证号、邮箱、银行卡、URL、IP、QQ 号等；支持自定义黑名单，命中关键词的消息整条丢弃，并在导入结果中给出分类统计。
- **全量备份**：一键导出单文件 JSON（人格、世界书、会话、消息、记忆、设置），导入侧支持三种去重策略与 `dry_run` 试算；导出的 `llm_api_key` 始终掩码。
- **轻量迁移**：启动时自动比对表结构并补齐缺失列，老库升级不丢数据。

### 工程与部署（已实现）

- Docker 镜像与 Compose 单服务部署，数据目录 `/app/data` 声明为卷。
- GitHub Actions CI：字节码编译、应用导入冒烟（校验路由数量）、前端语法检查、镜像构建。
- 零构建前端：`backend/static/` 开箱即用，无 npm、无打包、无外链 CDN。

> **未实现的能力一律不算特性**：语音播报、虚拟形象、主动消息、多角色群聊均属 Roadmap，请见[路线图](#路线图)。

---

## 快速开始

### 方式一：本地启动（零外部依赖）

要求：Python **3.11+**（无需 Node、无需数据库服务）。

```bash
cd cyber-girlfriend/backend

python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

打开 <http://localhost:8000>，默认 mock 模式，**不需要任何 API Key**。

- Windows 可双击 `scripts\run.bat`，macOS / Linux 可执行 `scripts/run.sh`（自动建虚拟环境、装依赖、启服务）。
- 首次启动会自动建库并写入示例人格；数据文件为 `backend/data/cyber_gf.db`。
- 想接真实模型：把 `backend/.env.example` 复制为 `backend/.env`，或在网页「设置」页填写（运行期配置优先级高于环境变量）。

### 方式二：Docker

```bash
# 在项目根目录
docker compose up -d --build
# 或
docker build -t cyber-girlfriend:0.2.0 .
docker run -p 8000:8000 -v "${PWD}/backend/data:/app/data" cyber-girlfriend:0.2.0
```

打开 <http://localhost:8000>。聊天记录通过 `./backend/data` 持久化，容器重建不丢数据。

> ⚠️ 默认**无鉴权**，请勿直接暴露到公网；远程访问请置于带认证的反向代理之后，详见 [SECURITY.md](SECURITY.md)。

---

## 目录结构

```
cyber-girlfriend/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口、静态挂载、/api/meta、/health
│   │   ├── api/               # 接口层（personas / cards / worldbook / importer /
│   │   │                      #   sessions / chat / memories / settings / feedback / backup）
│   │   ├── core/              # 配置（CG_ 前缀）与运行期配置
│   │   ├── db/                # 会话、建表、种子数据、轻量迁移
│   │   ├── models/            # 8 张表
│   │   ├── schemas/           # Pydantic 出入参
│   │   └── services/          # card / lore / importer / llm / memory / persona / chat
│   ├── static/                # 零构建前端（index.html / app.js / style.css / vendor）
│   ├── data/                  # 运行期 SQLite（不入库）
│   ├── requirements.txt
│   └── .env.example
├── docs/                      # ARCHITECTURE.md / PRIVACY.md
├── scripts/                   # run.bat / run.sh
├── .github/                   # CI 与 Issue / PR 模板
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── README.md / CHANGELOG.md / CONTRIBUTING.md / SECURITY.md / CODE_OF_CONDUCT.md
└── LICENSE
```

---

## API 概览

统一前缀 `/api`，交互式文档见 <http://localhost:8000/docs>。

| 模块 | 端点 | 说明 |
| --- | --- | --- |
| 元信息 | `GET /api/meta`、`GET /health` | 版本、是否演示模式、能力清单、健康检查 |
| 人格 | `GET/POST /api/personas`、`GET/PUT/DELETE /api/personas/{id}` | 人格增删改查 |
| 人格 | `POST /api/personas/generate`、`POST /api/personas/preview-prompt` | 从导入记录提取人设、Prompt 预览 |
| 角色卡 | `POST /api/cards/parse`、`POST /api/cards/import` | 解析预览（不落库）、导入建人格（含世界书） |
| 角色卡 | `GET /api/personas/{id}/card.json`、`GET /api/personas/{id}/card.png` | 导出 V1/V2/V3（JSON / PNG） |
| 世界书 | `GET/POST /api/personas/{id}/worldbook`、`POST /api/personas/{id}/worldbook/preview` | 条目列表 / 新建 / 命中测试 |
| 世界书 | `PUT/DELETE /api/worldbook/{entry_id}` | 条目更新 / 删除 |
| 导入 | `POST /api/import/upload`、`GET /api/import/batches`、`GET/DELETE /api/import/batches/{id}` | 上传记录（含脱敏统计）、批次管理 |
| 会话 | `GET/POST /api/sessions`、`GET/DELETE /api/sessions/{id}`、`GET /api/sessions/{id}/messages` | 会话与消息 |
| 对话 | `POST /api/chat/stream` | SSE 流式回复（`delta` / `notice` / `meta` / `error` / `done`） |
| 记忆 | `GET/POST /api/memories`、`PUT/DELETE /api/memories/{id}`、`POST /api/memories/search` | 记忆 CRUD 与检索 |
| 设置 | `GET/PUT /api/settings` | 运行期配置读写（API Key 掩码返回） |
| 反馈 | `GET/POST /api/messages/{id}/feedback` | 点赞 / 点踩 / 改写样本 |
| 备份 | `GET /api/backup/export`、`POST /api/backup/import` | 全量导出；导入支持 `merge_by_id` / `merge_by_name` / `skip_duplicates` 与 `dry_run` |

---

## 配置项

全部环境变量以 `CG_` 为前缀，可写在 `backend/.env`；网页「设置」页写入的值存 `app_configs` 表，**优先级高于环境变量**。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CG_DATABASE_URL` | 空（自动） | 为空时按代码位置解析为 `backend/data/cyber_gf.db` 的绝对路径（启动自动建目录）；Docker 内显式设为 `sqlite:////app/data/cyber_gf.db` |
| `CG_LLM_PROVIDER` | `mock` | `mock` / `openai`（任意 OpenAI 兼容网关）/ `ollama` |
| `CG_LLM_BASE_URL` | 空 | openai 兼容接口填到 `/v1`；ollama 填 `http://localhost:11434` |
| `CG_LLM_API_KEY` | 空 | API Key，写入后接口只返回掩码 |
| `CG_LLM_MODEL` | 空 | 模型名；为空时自动降级为 mock |
| `CG_LLM_TEMPERATURE` | `0.8` | 采样温度 |
| `CG_MEMORY_TOP_K` | `5` | 每轮召回记忆条数（1–50） |
| `CG_RECENT_WINDOW` | `12` | 携带的最近消息条数（1–100） |
| `CG_REFLECT_EVERY` | `6` | 每 N 条 AI 回复触发一次反思 |
| `CG_LORE_ENABLED` | `true` | 是否注入世界书 |
| `CG_LORE_BUDGET` | `1200` | 单轮世界书注入预算（字符近似 token） |
| `CG_LORE_SCAN_WINDOW` | `12` | 关键词匹配扫描的最近消息条数 |
| `CG_DESENSITIZE_ENABLED` | `true` | 导入是否自动脱敏 |
| `CG_DESENSITIZE_BLACKLIST` | 空 | 黑名单关键词，逗号 / 换行分隔或 JSON 数组；命中即整句丢弃 |

---

## 隐私与数据安全

聊天记录是本项目处理过的**最敏感数据**，请按以下事实使用：

1. **默认全本地**：人格、世界书、会话、消息、记忆全部存于本机 SQLite；只有当你配置了真实 Provider 时，拼装后的上下文才会发送给该服务。
2. **导入默认脱敏**：手机号、身份证号、邮箱、银行卡、URL、IP、QQ 号等会被替换为占位符；黑名单命中消息整条丢弃。但脱敏**不等于匿名化**，分享截图前请自行复核。
3. **备份文件是明文**：`GET /api/backup/export` 导出的 JSON 含全部聊天内容，仅 `llm_api_key` 掩码；请加密保管，勿放共享目录或公开仓库。
4. **不要公网裸奔**：默认无鉴权，任何能访问 8000 端口的人都能读取全部数据。详见 [SECURITY.md](SECURITY.md) 与 [docs/PRIVACY.md](docs/PRIVACY.md)。
5. **仓库不含数据**：`backend/data/`、`*.db`、`.env` 均已被 `.gitignore` / `.dockerignore` 排除。

---

## 路线图

以下**均未实现**，按优先级排列；欢迎在 Issue 中讨论方案或直接提 PR。

| 阶段 | 待办 | 说明 |
| --- | --- | --- |
| **P1** | 向量记忆召回 | 用 embedding 语义召回替代当前纯词法匹配，提升「换个说法也能想起来」的命中率；需引入可选依赖并保留纯词法回退 |
| **P1** | 主动消息 | 基于时间间隔、话题悬置与好感度，在用户未发言时主动发起消息；需设计免打扰与频率上限 |
| **P2** | TTS 语音 | 回复转语音播放，支持本地 TTS 与云端 API 两种后端；不做实时双工语音 |
| **P2** | 多角色群聊 | 一个会话内多位人格参与，需解决发言调度、上下文隔离与记忆归属 |

已经落地的能力见 [CHANGELOG.md](CHANGELOG.md)，不做超前承诺。

---

## 参与贡献

- 贡献流程与代码风格：[CONTRIBUTING.md](CONTRIBUTING.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 安全漏洞请**私下**上报：[SECURITY.md](SECURITY.md)
- 架构与模块说明：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 许可证与免责声明

本项目基于 [MIT License](LICENSE) 开源。

- 仅供个人学习、研究与自娱自乐；请勿用于冒充真实他人、骚扰、诈骗或任何违法用途。
- 导入的聊天记录涉及他人隐私，请确保你拥有合法处理权，并自行承担合规责任。
- 角色卡版权归原作者所有；导入第三方角色卡请遵守其授权条款。
- AI 生成内容可能不准确、不合时宜，请自行甄别；请勿将本项目用于未成年人相关场景。

---

# English Overview

**cyber-girlfriend** is a local-first AI companion app. It imports an exported chat history (WeChat / QQ / Telegram / CSV / plain text), extracts a persona — verbal tics, emoji habits, sentence length, style sliders and real sample dialogues — and then chats with you using **three-layer memory** (recent window, session summary, long-term memories). Everything is stored in a local SQLite file; no cloud account is required, and no API key is needed to try it out.

Stack: **Python 3.11+ / FastAPI + SQLAlchemy 2.0 + SQLite**, with a **zero-build Vue 3 SPA** (no npm, no bundler, no CDN). Current version: `0.2.0`. License: MIT.

## Comparison

Orientation only — not a ranking. Details of other projects follow their public docs and may change.

| Aspect | cyber-girlfriend | SillyTavern | WeClone | Open-LLM-VTuber |
| --- | --- | --- | --- | --- |
| Focus | Self-hosted app: chat history → persona → memory | Role-play frontend for LLMs | Fine-tune a digital twin on WeChat logs | Voice chat client with Live2D avatar |
| Runtime | One Python process + SQLite + static SPA | Node frontend, bring your own backend | GPU training pipeline, produces weights | LLM + ASR + TTS stack |
| Persona from chat logs | ✅ Built in | ❌ (cards / manual) | ✅ as training data only | ❌ |
| SillyTavern character cards (V1/V2/V3, PNG-embedded) | ✅ import & export | ✅ native, richest ecosystem | ❌ | Partial (plugin) |
| Lorebook / World Info | ✅ keyword + constant, position/depth/budget | ✅ more complete | ❌ | ❌ |
| Long-term memory | ✅ three layers, automatic reflection, no extra component | Via extensions | Encoded in weights | Depends on the LLM context |
| Voice / avatar | ⛔ Not implemented (P2) | Via extensions | ⛔ | ✅ real-time voice + Live2D |
| Deployment cost | Low: pip install or one Docker command | Medium | High (GPU) | Medium-high |

## Features

- **Chat log import**: auto-detects WeChat / QQ txt, Telegram JSON, generic JSON/CSV and `Name: message` text (24MB limit), with speaker stats and preview.
- **Persona extraction**: verbal tics, emoji/punctuation habits, average sentence length, sample dialogues and five heuristic style sliders.
- **Character card interop**: import/export SillyTavern V1/V2/V3 cards as JSON or PNG (reads `tEXt`/`zTXt`/`iTXt` chunks, `chara` and `ccv3`); embedded `character_book` becomes lorebook entries.
- **Lorebook**: constant or keyword-triggered entries with priority, case sensitivity, injection position/depth and a character budget, plus a hit-test preview.
- **Streaming chat**: SSE token stream with stop button; message regeneration, copy, and edit-and-resend; Markdown rendering with escape-first XSS protection.
- **Three-layer memory**: recent window + rolling summary + long-term memories recalled by lexical similarity × time decay × importance, with periodic reflection.
- **Privacy by default**: import-time desensitization (phone, ID card, email, bank card, URL, IP, QQ) with a custom blocklist that drops whole messages; full JSON backup/restore with masked API keys; automatic additive DB migration.
- **Ops ready**: Dockerfile + Compose (volume at `/app/data`), GitHub Actions CI (compile, import smoke test, frontend syntax check, image build).

**Not implemented** (see Roadmap): TTS, avatar, proactive messages, multi-character group chat.

## Quick Start

**Local** (Python 3.11+, no Node, no external DB):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>. The default `mock` provider needs no API key. On Windows you can double-click `scripts\run.bat`; on macOS/Linux run `scripts/run.sh`.

**Docker**:

```bash
docker compose up -d --build
# or
docker build -t cyber-girlfriend:0.2.0 .
docker run -p 8000:8000 -v "${PWD}/backend/data:/app/data" cyber-girlfriend:0.2.0
```

Data persists in `./backend/data`. The app ships **without authentication** — never expose port 8000 directly to the internet; put it behind an authenticated reverse proxy.

**API**: everything lives under `/api` (interactive docs at `/docs`). Main groups: `personas`, `cards`, `worldbook`, `import`, `sessions`, `chat/stream`, `memories`, `settings`, `messages/{id}/feedback`, `backup`.

## Privacy & Data Safety

- All personas, lorebook entries, sessions, messages and memories stay in a local SQLite file; only if you configure a real provider is the assembled context sent to that service.
- Import-time desensitization is on by default, but it is **not anonymization** — review before sharing screenshots.
- Exported backups are **plaintext JSON** containing full conversations (`llm_api_key` is masked). Store them encrypted.
- `backend/data/`, `*.db` and `.env` are excluded from git and from the Docker build context.
- Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## Roadmap

- **P1**: vector-based memory recall (embedding recall with lexical fallback); proactive messages with quiet hours and rate limits.
- **P2**: TTS playback; multi-character group chat with turn scheduling and per-character memory scope.

## License

MIT — see [LICENSE](LICENSE). For personal use only; do not use it to impersonate real people, harass, or defraud. Chat logs involve other people's privacy: make sure you have the right to process them.
*（内容由AI生成，仅供参考）*
