---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 4574a99947de89212c009903f0fa961d_544de5d9cdf411f1a475525400248c00
    ReservedCode1: kWghuFqZNEM8d3s9qMdWbTMtl9vLMHB+5B0wYFMP1GCgdrjMQcaSgZXyVuR5/5ZBE/IKpYqd/OuEw99Y+1ey07YdlyvMkIB3afMTVTR+ZD/2kWL9hIhc4z792xeGpLXF4V0PS47NxTCcdmn9Ylhlqx+nk2EKSEeD4zwFezOcacoXd/lJk/mhPxhrbYk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 4574a99947de89212c009903f0fa961d_544de5d9cdf411f1a475525400248c00
    ReservedCode2: kWghuFqZNEM8d3s9qMdWbTMtl9vLMHB+5B0wYFMP1GCgdrjMQcaSgZXyVuR5/5ZBE/IKpYqd/OuEw99Y+1ey07YdlyvMkIB3afMTVTR+ZD/2kWL9hIhc4z792xeGpLXF4V0PS47NxTCcdmn9Ylhlqx+nk2EKSEeD4zwFezOcacoXd/lJk/mhPxhrbYk=
---

# 安全策略 / Security Policy

## 敏感数据声明

**本项目的核心数据是聊天记录，属于最高等级的隐私数据。** 一次导入可能包含你和真实联系人的完整对话、手机号、住址、订单、身份证号等信息。请务必在部署与反馈问题前阅读以下内容。

- 数据默认**全部保存在本机** `backend/data/cyber_gf.db`（Docker 下为挂载卷 `/app/data`），不会上传到任何服务器；只有当你配置了 `openai` / `ollama` 等真实 Provider 时，**拼装后的对话上下文**才会发送给该 Provider。
- 导出备份（`GET /api/backup/export`）生成的是**明文 JSON**，内含人格、世界书、会话、消息与记忆，仅 `llm_api_key` 做了掩码。请把它当作身份证级别的文件保管，不要放进网盘共享目录或公开仓库。
- 导入与角色卡解析默认开启脱敏（手机号、身份证、邮箱、银行卡、URL、IP、QQ 等替换为占位符；命中黑名单关键词的整句丢弃），但**脱敏不等于匿名化**，仍可能残留可识别信息，请自行复核后再分享任何截图或文件。
- `.env`、`*.db`、`backend/data/` 已被 `.gitignore` 与 `.dockerignore` 排除，请勿取消忽略规则。

## 支持的版本

| 版本 | 是否接受安全修复 |
| --- | --- |
| 0.2.x（当前开发线） | 是 |
| 0.1.x | 否，请先升级 |

修复以最新代码为准；不承诺为旧版本回补补丁。

## 漏洞上报方式（请勿公开）

**不要**通过公开 Issue、PR、Discussion 或社交平台披露安全漏洞，也不要附带真实聊天记录作为复现数据。

推荐渠道：

1. **GitHub 私密漏洞报告**：仓库页面 → `Security` → `Advisories` → `Report a vulnerability`（Private vulnerability reporting）。这是首选方式，可直接与维护者私下沟通并协同修复。
2. 若仓库维护者在 README 中公布了其他私下联系方式，也可直接联系；请勿使用公开评论区。

上报内容建议包含：

- 受影响的版本 / commit；
- 漏洞类型与影响（例如：任意文件读取、密钥泄露、XSS、越权访问）；
- 最小复现步骤（**使用自行编造的假数据**）；
- 你的修复建议（可选）。

## 处理流程

- **确认收到**：尽力在 7 天内回复。
- **评估与修复**：确认后在私有分支修复，必要时发布补丁版本并在 CHANGELOG 的 `Security` 段落说明。
- **披露**：修复发布后再公开致谢与细节；如你希望匿名，请在报告中注明。
- 本流程为维护者的善意承诺，不构成商业 SLA。

## 重点关注的风险面

欢迎针对以下方向做安全测试（仅限你自己的实例）：

- 上传接口（`/api/cards/parse`、`/api/cards/import`、`/api/import/upload`、`/api/backup/import`）的文件类型、体积与畸形输入处理；
- 角色卡 PNG 解析与导出（内嵌 `tEXt`/`zTXt`/`iTXt` 数据的边界处理）；
- 备份导入的 ID 重映射与设置覆盖逻辑（是否会写入非预期配置）；
- 设置接口对 API Key 的打码是否可被绕过读取；
- 前端 Markdown 渲染的 XSS 防护（先转义后替换）；
- 静态资源与数据目录的越权访问（路径穿越）。

## 部署加固建议

- **不要直接把 8000 端口暴露到公网**。默认无鉴权，任何能访问该端口的人都能读取全部聊天记录。需要远程访问时，请置于带身份认证的反向代理（Nginx / Caddy / Tailscale 等）之后，或仅监听 `127.0.0.1`。
- Docker 部署时确认挂载目录 `./backend/data` 的宿主机权限，避免被同机其他账户读取。
- 真实 API Key 建议只通过环境变量或设置页写入，不要写进镜像、compose 文件或提交到仓库。
- 定期导出备份后加密存放（如 7z / age 加密），并清理不再需要的旧备份文件。
- 分享部署截图前，先确认界面上没有真实姓名、头像与聊天内容。
*（内容由AI生成，仅供参考）*
