---
type: entity
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [product, platform, sciweave]
---

# SciWeave

SciWeave 是面向科研小组的科研协作与智能体平台。它以版本化研究路线为主线，把任务执行、结果接纳、路线变更、候选审核和正式发布组织为可追溯、可审计的闭环。

## 产品组成

| 组成 | 作用 | 事实状态 |
|---|---|---|
| Research Mapping | 用 `TaskNode` 与 `DependencyEdge` 表达版本化研究路线 | 已有领域服务、管理 MCP、TerminusDB/SQLite 存储与测试 |
| LLM-Wiki | 管理 Wiki 文档、资源版本、引用资格和正式修订 | 已有领域服务、管理 MCP、存储与测试 |
| Draft Buffer | 保存尚未进入领域候选的 Mapping/Wiki 草稿 | 服务、MCP 与测试已实现 |
| Task Agent | 在研究员端执行正式任务并产出草稿 | 套件和 runtime 已有大量测试；端侧部署依赖宿主配置 |
| Centre Agent | 对 Mapping/Wiki 候选执行预审并提供报告 | 设计边界明确；事件消费的文档与实现状态存在冲突 |
| Project Owner 套件 | 预览、审核、正式化候选并派发根任务 | 可安装套件目录已存在 |
| Coordinator | 根据正式快照重算依赖并发布可执行交接或通知 | 独立中央服务已存在 |
| Registry / Email / Dashboard | 主体登记、通知投递、只读运营视图 | 对应服务和前端已存在 |

## 核心原则

- 正式领域内容按精确的数据库、分支和 Commit 读取，不用“最新版本”替代正式版本。
- 候选、正式版本、草稿和执行记录分属不同状态边界。
- 消息队列负责交接与事件传递；MCP 主要提供领域治理和人工处置接口。
- Registry 是事实登记，不是授权系统；正式 Mapping 中的 `executor_refs` 才是执行关系依据。
- 审计位于对外 MCP 接口层和领域治理边界，不能用邮件或客户端自报角色替代。

## 相关页面

- [[concepts/research-mapping-and-wiki]]
- [[concepts/core-flow]]
- [[concepts/work-agents-and-governance]]
- [[concepts/deployment-and-operations]]
- [[syntheses/status-and-risks]]
