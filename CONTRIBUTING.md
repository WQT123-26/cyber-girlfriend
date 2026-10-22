---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_524bea49cdf411f1a475525400248c00
    ReservedCode1: KkXomV0Ng2za1c3u125QBaPMy4eiJjIifRzBrVspi3+/040o1nwww7TjrE3rdp+v/FPeI3LwM4Dtg7fZXQf6JmxwW4LjJq9ZiqXGpYKLURee7xTyPwdZ+fuHq8Cwsu/Km3TAFyogt6E7Uat4nHwLLWB9IK+ZYws9Xl7npbRBS100RlDTlIIOK/M/Zu8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_524bea49cdf411f1a475525400248c00
    ReservedCode2: KkXomV0Ng2za1c3u125QBaPMy4eiJjIifRzBrVspi3+/040o1nwww7TjrE3rdp+v/FPeI3LwM4Dtg7fZXQf6JmxwW4LjJq9ZiqXGpYKLURee7xTyPwdZ+fuHq8Cwsu/Km3TAFyogt6E7Uat4nHwLLWB9IK+ZYws9Xl7npbRBS100RlDTlIIOK/M/Zu8=
---

# 贡献指南 / Contributing to cyber-girlfriend

感谢你愿意参与「赛博女友」。这是一个**本地优先、零构建、轻依赖**的项目：后端是 FastAPI + SQLite，前端是单文件 Vue 3 SPA（无 Node 构建、无 CDN）。请在动手前花几分钟读完本文，能省下大量来回沟通。

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全相关问题请**不要**开 Issue，按 [SECURITY.md](SECURITY.md) 私下上报。

---

## 1. 开发环境准备

要求：Python **3.11+**（CI 使用 3.11），可选 Docker。

```bash
git clone <your-fork-url> cyber-girlfriend
cd cyber-girlfriend/backend

# 1) 虚拟环境
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate

# 2) 依赖（仅 7 个纯 Python 包，无需编译）
pip install -r requirements.txt

# 3) 可选配置：不配也能跑（默认 mock 模式）
# Windows: copy .env.example .env    macOS/Linux: cp .env.example .env

# 4) 启动
python -m uvicorn app.main:app --reload --port 8000
```

打开 <http://localhost:8000> 即可。数据库首次启动时自动创建在 `backend/data/cyber_gf.db`，**该目录已被 `.gitignore` 忽略，请不要提交**。

也可用一键脚本：`scripts/run.bat`（Windows）/ `scripts/run.sh`（macOS、Linux），或 `docker compose up --build`。

---

## 2. 目录结构

```
cyber-girlfriend/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口：路由聚合、静态挂载、/api/meta、/health
│   │   ├── api/                 # 接口层（只做参数校验与编排，不写业务逻辑）
│   │   │   ├── personas.py      # 人格 CRUD、人设生成、Prompt 预览
│   │   │   ├── cards.py         # 角色卡解析/导入/导出（V1/V2/V3、PNG 内嵌）
│   │   │   ├── worldbook.py     # 世界书条目 CRUD 与命中预览
│   │   │   ├── importer.py      # 聊天记录上传与批次管理
│   │   │   ├── sessions_api.py  # 会话列表、详情、删除
│   │   │   ├── chat.py          # SSE 流式对话
│   │   │   ├── memory.py        # 记忆 CRUD 与检索
│   │   │   ├── settings_api.py  # 运行期配置读写（API Key 打码）
│   │   │   ├── feedback.py      # 点赞 / 改写样本
│   │   │   └── backup.py        # 全量备份导出与导入
│   │   ├── core/                # 配置（CG_ 前缀环境变量）、运行期配置读写
│   │   ├── db/                  # SQLAlchemy 会话、建表、轻量加列迁移
│   │   ├── models/models.py     # 8 张表：personas / worldbook_entries / sessions /
│   │   │                        #        messages / memories / feedbacks /
│   │   │                        #        import_batches / app_configs
│   │   ├── schemas/schemas.py   # Pydantic 出入参
│   │   └── services/            # 业务服务
│   │       ├── card/            # 角色卡 V1/V2/V3 解析与 PNG tEXt 读写
│   │       ├── lore/            # 世界书关键词匹配与预算控制
│   │       ├── importer/        # 聊天记录解析 + 脱敏
│   │       ├── llm/             # Provider 抽象与实现（mock/openai/ollama）
│   │       ├── memory/          # 记忆存储与反思
│   │       ├── persona/         # 人设提取、Prompt 组装
│   │       └── chat/            # 对话编排（拼上下文 → 调 LLM → 落库）
│   ├── static/                  # 前端：index.html / app.js / style.css / vendor/
│   ├── data/                    # 运行期 SQLite（不入库）
│   ├── requirements.txt
│   └── .env.example
├── docs/                        # ARCHITECTURE.md、PRIVACY.md
├── scripts/                     # run.bat / run.sh
├── .github/                     # CI 与 Issue/PR 模板
├── Dockerfile / docker-compose.yml / .dockerignore
└── README.md / CHANGELOG.md / CONTRIBUTING.md / SECURITY.md / CODE_OF_CONDUCT.md
```

---

## 3. 代码风格

- **Python**：4 空格缩进；文件头使用 `from __future__ import annotations`；公共函数与类写中文 docstring；对外函数标注类型；遵循 PEP 8，行宽建议 ≤ 110。
- **分层纪律**：`api/` 只做入参校验、权限/存在性检查与响应组装；真正的逻辑放 `services/`；**禁止**在 `api/` 里堆业务算法。
- **依赖纪律**：不引入需要编译或体积庞大的依赖（如 jieba、numpy、chromadb）。中文分词、向量计算等能力用标准库实现；确需新增依赖，必须在 PR 描述里说明理由与体积影响。
- **前端**：`backend/static/` 为**零构建**目录，禁止引入打包工具、CDN 与 `npm` 依赖；`vendor/vue.global.prod.js` 属随仓库分发资源，不要删除。模板内渲染用户内容必须先转义再替换 Markdown，避免 XSS。
- **数据库**：新增字段时同步更新 `app/db/migrate.py` 的加列逻辑（`PRAGMA table_info` 检查 + `ALTER TABLE`），保证老库升级不丢数据；不要写破坏性迁移。
- **文案**：界面与提示语以中文为主；日志与注释保持简洁，不输出用户聊天原文。

提交前自检：

```bash
cd backend
python -m compileall -q app
node --check static/app.js      # 仅改动前端时
```

CI 会执行同样的检查，并额外做一次应用导入冒烟（路由数量 > 20）与镜像构建。

---

## 4. 提交信息规范（Conventional Commits）

格式：

```
<type>(<scope>): <subject>

<body 可选>

<footer 可选，如 Closes #12 / BREAKING CHANGE: ...>
```

常用 `type`：`feat` 新功能、`fix` 修复、`refactor` 重构、`perf` 性能、`docs` 文档、`style` 格式、`test` 测试、`build` 构建、`ci` CI、`chore` 杂项。

常用 `scope`：`api`、`card`、`lore`、`importer`、`memory`、`llm`、`chat`、`settings`、`backup`、`frontend`、`docs`、`docker`、`ci`。

示例：

```
feat(lore): 支持按 position 与 depth 注入世界书条目

- 新增 before_char / after_char / at_depth 三种注入位置
- 命中后按 priority 降序与字符预算裁剪

Closes #18
```

```
fix(frontend): 流式回复持有裸对象导致气泡不更新

改为 push 后通过 state.messages[idx] 代理累加
```

一个提交只做一件事；不要把格式化改动与功能改动混在同一个 commit 里。

---

## 5. PR 流程

1. 先开 Issue 或在已有 Issue 下认领，避免重复劳动；大型改动请先讨论方案。
2. Fork 仓库，从 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
3. 按上文自检，并确保 **mock 模式**下功能可跑通（评审不会为你准备 API Key）。
4. 更新文档：接口变更同步 `docs/ARCHITECTURE.md` 与 README 的 API 概览表；面向用户的行为变更记入 `CHANGELOG.md` 的 `Unreleased`。
5. 提交 PR，按 `.github/PULL_REQUEST_TEMPLATE.md` 填写；关联 `Closes #id`。
6. 通过 CI（编译 / 冒烟 / 前端语法 / 镜像构建）后由维护者评审合并。

评审关注点：数据安全（是否泄露聊天记录或密钥）、老库兼容、mock 模式可用性、是否引入重依赖。

---

## 6. 如何新增一个 LLM Provider

以新增 `anthropic` 为例，共 5 步，全部集中在 `backend/app/services/llm/`：

**① 实现子类** —— 新建 `anthropic.py`，继承 `LLMProvider`，只需实现 `stream()`：

```python
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from app.services.llm.base import LLMProvider, LLMError, normalize_messages


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def stream(self, messages: Any, **kw: Any) -> AsyncIterator[str]:
        payload = {"model": self.model, "messages": normalize_messages(messages), "stream": True}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/messages", json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    raise LLMError(f"anthropic 返回 {resp.status_code}")
                async for line in resp.aiter_lines():
                    ...  # 解析 SSE，逐块 yield 文本
```

**② 注册到工厂** —— `factory.py`：导入新类，在 `build_provider()` 增加分支，并把 `"anthropic"` 加入 `PROVIDER_NAMES`。缺 `base_url` / 模型名时必须**降级为 `MockProvider`**（可用 `fallback_reason`），保证零配置仍能跑。

**③ 暴露到前端** —— `app/api/settings_api.py` 的 `build_settings_out()` 中 `provider_options` 自动来自硬编码列表，请同步追加；设置页下拉即可出现。

**④ 环境变量** —— 复用现有 `CG_LLM_BASE_URL` / `CG_LLM_API_KEY` / `CG_LLM_MODEL` / `CG_LLM_TEMPERATURE`，无需新增。

**⑤ 文档** —— README 的 Provider 表、`.env.example` 注释、`docs/ARCHITECTURE.md` 的 Provider 小节同步更新。

约定：`stream()` 必须是**异步生成器**；异常统一抛 `LLMError`；不要在 Provider 里做脱敏或落库（那是 `services/importer` 与 `services/chat` 的职责）。

---

## 7. 如何新增一种聊天记录导入格式

解析器在 `backend/app/services/importer/parser.py`，自动识别、无需用户选择格式。

1. **登记扩展名**：如需支持新后缀，改 `SUPPORTED_EXTS`（当前 `.txt` / `.json` / `.csv`）。
2. **写识别与解析函数**：例如 `_parse_discord_json(text)`，返回 `(fmt, messages)`；`messages` 每项为 `{"speaker": str, "content": str, "timestamp": str|None}`。
3. **接入探测顺序**：在 `parse_bytes()` 的分支链里按「特征越强越靠前」插入（json → csv → 微信 → QQ → 通用 `昵称: 内容`）；探测必须**宽容失败**，识别不了就交给下一个分支，不能直接抛错。
4. **统一后处理**：消息列表交给 `_finalize()`（统计 speakers、截断至 `MAX_MESSAGES=20000`、生成 preview），脱敏由 `desensitize_messages()` 统一执行，**不要**在解析函数里自己打码。
5. **保持统计字段**：返回体需含 `fmt`、`messages`、`speakers`、`message_count`、`raw_message_count`、`preview`、`desensitize`，前端预览页依赖这些字段。
6. **验证**：用一段脱敏后的样例文本验证：条数、说话人统计、时间戳解析、黑名单整句丢弃、超长文件（>24MB 应被 API 拒绝）。

新增格式请附一份**造假的**样例（`tests/fixtures` 或 PR 描述内），禁止提交真实聊天记录。

---

## 8. 文档与版本

- 版本号在 `backend/app/main.py` 的 `FastAPI(version=...)` 与 `CHANGELOG.md` 保持一致。
- `CHANGELOG.md` 遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，未发布内容写在 `[Unreleased]` 的 Added / Changed / Fixed / Security 下。
- 涉及隐私相关能力（导入、备份、脱敏）的改动，必须同步 `docs/PRIVACY.md`。

---

## 9. 不要做的事

- 不要提交 `backend/data/`、任何 `*.db`、`.env` 或含真实 API Key 的截图。
- 不要在仓库、Issue、PR 里粘贴真实聊天记录或他人隐私信息。
- 不要为了让 demo「看起来更强」而虚构已实现能力；未实现的功能一律写进 Roadmap。
- 不要绕过 `services/` 在 `api/` 里直连数据库做业务计算。

再次感谢你的贡献。
*（内容由AI生成，仅供参考）*
