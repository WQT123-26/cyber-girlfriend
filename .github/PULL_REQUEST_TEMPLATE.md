---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_590f35e0cdf411f1a475525400248c00
    ReservedCode1: BERXNHzyZPkQ7TcIL49leJQETciVtyAJL1umyjh3rGah7dGnlSwxJIPsDM3rJ7Xwv7Sh4rXK7QYOcCnDGDeDwxBHlmuDNj8bNwh1w395lGqBLhTceqDS03f/9e7jEk2tHFYiPkAwjfPp3HketUFHCUlBcTU8wCkbTvb1jZzBGKwM0hlSb2M6CrRyuGc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_590f35e0cdf411f1a475525400248c00
    ReservedCode2: BERXNHzyZPkQ7TcIL49leJQETciVtyAJL1umyjh3rGah7dGnlSwxJIPsDM3rJ7Xwv7Sh4rXK7QYOcCnDGDeDwxBHlmuDNj8bNwh1w395lGqBLhTceqDS03f/9e7jEk2tHFYiPkAwjfPp3HketUFHCUlBcTU8wCkbTvb1jZzBGKwM0hlSb2M6CrRyuGc=
---

# Pull Request / 合并请求

## 变更类型 / Type of change

- [ ] 修复缺陷（fix）
- [ ] 新增功能（feat）
- [ ] 重构 / 性能优化（refactor / perf）
- [ ] 文档（docs）
- [ ] 工程化 / CI / Docker（chore / ci / build）
- [ ] **破坏性变更**（BREAKING CHANGE，需在下方说明迁移方式）

## 这个 PR 做了什么 / What does this PR do

<!-- 一段话概括；关联 Issue 请写 Closes #123 -->

## 关联 Issue

Closes #

## 改动范围 / Scope

<!-- 勾选并列出关键文件，便于评审快速定位 -->

- [ ] `backend/app/api/`（接口层）
- [ ] `backend/app/services/`（业务服务：card / lore / importer / chat / memory / llm）
- [ ] `backend/app/models` / `schemas` / `db`
- [ ] `backend/static/`（前端，零构建）
- [ ] 文档（README / docs / CHANGELOG）
- [ ] 工程化（Dockerfile / compose / .github）

## 自检清单 / Checklist

- [ ] `python -m compileall app` 通过（在 `backend/` 下执行）
- [ ] 如改前端，`node --check backend/static/app.js` 通过
- [ ] 未提交任何真实聊天记录、`*.db`、`.env` 或 API Key
- [ ] 新增/变更的 API 已同步到 `docs/ARCHITECTURE.md` 与 README 的 API 概览表
- [ ] 面向用户的行为变更已写入 `CHANGELOG.md` 的 `Unreleased`
- [ ] 如涉及数据库字段，已确认 `app/db/migrate.py` 能完成轻量加列迁移（不破坏老库）
- [ ] 兼容默认 mock 模式（无 Key 环境下仍可跑通）

## 破坏性变更说明 / Breaking change notes

<!-- 若无请写“无”。含 API 路径、请求体、数据库结构、配置项默认值的改动都需说明 -->

## 截图 / Screenshots

<!-- 前端改动请附改动前后对比 -->
*（内容由AI生成，仅供参考）*
