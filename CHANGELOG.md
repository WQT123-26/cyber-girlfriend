---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_5551d3d1cdf411f1a475525400248c00
    ReservedCode1: ZfZmjCNUsywdTFdl3QhtOms51ub3GYQYK7ymjzHV+bZDuLmDr6Dh9ZTa8uuHhhL24AW0fxCJDRglcs/3jPAzhVyqij5Ns0eAS1fOUCe2/0/uq2EDxs5+vURsJSpXNwDIRPU3N0c1MfrU6D8heeMNdDOl5PuDTMyBYnqmNRJnqghr1v3hGiFfhoQlPtc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_5551d3d1cdf411f1a475525400248c00
    ReservedCode2: ZfZmjCNUsywdTFdl3QhtOms51ub3GYQYK7ymjzHV+bZDuLmDr6Dh9ZTa8uuHhhL24AW0fxCJDRglcs/3jPAzhVyqij5Ns0eAS1fOUCe2/0/uq2EDxs5+vURsJSpXNwDIRPU3N0c1MfrU6D8heeMNdDOl5PuDTMyBYnqmNRJnqghr1v3hGiFfhoQlPtc=
---

# 更新日志 / Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.2.0] - 2026-10-22

本轮迭代主题：**从「能跑的 demo」到「能长期用的本地应用」**——角色卡互通、上下文可控、数据可迁移、前端可日常使用。

### Added

- **SillyTavern 角色卡导入导出（V1 / V2 / V3）**
  - 解析：`.json` 与 `.png`（读取 PNG 的 `tEXt` / `zTXt` / `iTXt` 块，兼容 `chara` 与 `ccv3` 两种键名），单文件上限 8MB。
  - 映射：`description` / `personality` / `scenario` / `first_mes` / `mes_example` / `system_prompt` / `post_history_instructions` / `alternate_greetings` / `creator_notes` / `character_version` / `tags` → 人格字段；内嵌 `character_book` → 该人格的世界书条目。
  - 导出：`GET /api/personas/{id}/card.json` 与 `GET /api/personas/{id}/card.png`（`spec=v1|v2|v3`，PNG 支持 `size` 指定占位底图边长 64–1024）。
  - 新接口：`POST /api/cards/parse`（仅预览摘要，不落库）、`POST /api/cards/import`（解析 → 脱敏 → 建人格）。
- **世界书 / Lorebook 关键词注入**
  - 新表 `worldbook_entries`，挂在人格维度；支持 `constant`（常驻）与关键词触发两种模式。
  - 匹配支持 `keys`（含大小写敏感开关）、`priority` 排序、`position`（`before_char` / `after_char` / `at_depth`）、`depth`、`token_budget` 字符预算裁剪。
  - 新接口：`GET/POST /api/personas/{id}/worldbook`、`POST /api/personas/{id}/worldbook/preview`（命中试跑）、`PUT/DELETE /api/worldbook/{id}`。
  - 新增配置：`lore_enabled`、`lore_budget`、`lore_scan_window`。
- **聊天记录导入脱敏**
  - 默认开启，覆盖手机号、身份证号、邮箱、银行卡、URL、IP、QQ 号等类别，按固定顺序替换为占位符；支持自定义黑名单，命中关键词的消息**整条丢弃**。
  - 导入返回体新增 `desensitize_enabled` 与 `desensitize` 统计（分类命中数、被丢弃条数）；前端预览页以统计卡片展示。
  - 新增配置：`desensitize_enabled`、`desensitize_blacklist`。
  - 角色卡导入的文本字段同样走脱敏（人格名保留原文）。
- **全量备份导出 / 导入**
  - `GET /api/backup/export`：导出单文件 JSON（`format` / `format_version` / `counts` / `settings` / `personas`（含 worldbook、memories、sessions、messages）），可选包含反馈样本与导入批次；`llm_api_key` 一律掩码，另给出 `llm_api_key_set` 布尔标记。
  - `POST /api/backup/import`：支持 `strategy=merge_by_id|merge_by_name|skip_duplicates`、`dry_run` 试算、`import_api_key` 显式开关（默认忽略密钥），返回逐表 created / skipped / remapped 报告；上限 64MB。
- **轻量数据库迁移**
  - 启动时用 `PRAGMA table_info` 比对期望列，缺失则 `ALTER TABLE ADD COLUMN` 补齐，老库升级不需要手工改表、不丢数据。
- **前端能力补齐**
  - 消息支持 Markdown 渲染（**先整体转义再替换**，避免 XSS）、重生成、复制、编辑后重发。
  - 新增角色卡导入面板与导出（JSON / PNG、V1/V2/V3 选择）、世界书面板（编辑 + 命中测试）、备份导出导入面板、导入脱敏统计卡片。
  - 设置页补齐世界书与脱敏共 5 项配置。
- **工程化**
  - 新增 `Dockerfile`（python:3.11-slim，仅安装 7 个纯 Python 依赖、暴露 8000、`/app/data` 声明为卷）、`docker-compose.yml`（单服务、端口 8000、数据持久化、环境变量示例）、`.dockerignore`。
  - 新增 GitHub Actions CI：Python 3.11 安装依赖 → `python -m compileall app` → 导入 `app.main` 校验路由数量 → 前端 `node --check` → 镜像构建。
  - 新增 Issue / PR 模板、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、本 CHANGELOG；README 改写为中英双语并补充同类项目差异对比与路线图。

### Changed

- 数据库由 7 张表扩展为 8 张表（新增 `worldbook_entries`），`import_batches` 增加脱敏相关字段。
- `GET /api/settings` 返回体新增 `lore_*`、`desensitize_*`、`provider_options`、`desensitize_rules` 等字段。
- `/api/meta` 的 `features` 列表补充角色卡、世界书、脱敏、备份能力标记。
- 备份导入默认**不导入** `llm_api_key`，避免把掩码串写回数据库。

### Fixed

- 流式回复持有裸消息对象导致气泡内容不更新：改为 push 后通过 `state.messages[idx]` 代理累加。
- `PUT /api/settings` 引用的 `reset_provider_cache` 未定义导致保存设置时 ImportError。
- 页面缺少 favicon 产生 404；密码输入框补充 `autocomplete` 提示。

### Security

- 备份文件与设置接口中的 API Key 统一掩码输出，避免密钥经响应或导出文件泄露。
- 导入路径默认脱敏，降低把真实联系人信息带入人格与 Prompt 的风险。
- 前端 Markdown 渲染采用「先转义、后替换」策略，阻断聊天内容注入 HTML。

## [0.1.0] - 2026-10-22

首个可运行版本（P0 demo）。

### Added

- **后端**：FastAPI + SQLAlchemy + SQLite，启动自动建库建表；提供 `/health` 与 `/api/meta`；静态资源挂载，`GET /` 返回 SPA。
- **前端**：单文件 Vue 3 SPA（零构建、无 CDN），含角色墙、导入向导、聊天、人设编辑、记忆库、设置六个视图。
- **人格**：人格 CRUD、人设自动提取（从导入的聊天记录中提取说话人特征）、Prompt 预览。
- **导入**：自动识别微信 PC 端 txt、QQ 消息管理器 txt、Telegram Desktop json、通用 json / csv 与「昵称: 内容」纯文本；生成导入批次供预览与挑选说话人。
- **对话**：SSE 流式输出（`delta` / `notice` / `meta` / `error` / `done` 事件），回复落库并更新心情与好感度。
- **记忆**：三层结构——近期窗口、关键词召回、周期性反思摘要。
- **LLM**：Provider 抽象 + `mock` / `openai`（OpenAI 兼容）/ `ollama` 三种实现；未配置时自动降级 mock，零 Key 可完整体验。
- **设置**：运行期配置存 `app_configs` 表，DB 值优先于环境变量；API Key 返回时打码。
- **反馈**：消息点赞 / 点踩与改写样本留存。
- **文档与脚本**：README、`docs/ARCHITECTURE.md`、`docs/PRIVACY.md`、`LICENSE`（MIT）、`.gitignore`、`scripts/run.bat`、`scripts/run.sh`。

### Security

- 默认纯本地运行，数据仅存本机 SQLite；`data/`、`*.db`、`.env` 均已忽略，不随仓库分发。

> 版本对比链接待仓库地址确定后补充（形如 `https://github.com/<owner>/<repo>/compare/v0.1.0...v0.2.0`）。
*（内容由AI生成，仅供参考）*
