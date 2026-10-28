---
type: concept
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [agents, permissions, governance, mcp]
---

# Work Agent 与治理角色

Work Agent 是统一架构的上位概念，包含研究员侧的 Task Agent 和中央服务器的 Centre Agent。两者都由常驻 Gateway（MCP + subscriber）和短生命周期 Worker 构成，共享 SQLite 状态机与本地 Worker Lease，但订阅事件和执行目标不同。

## 角色职责

| 角色 | 能做 | 明确不能做 |
|---|---|---|
| Task Agent | 执行正式分配的科研任务，产出草稿 | 不能把草稿自动变成候选或正式版本 |
| Centre Agent | 读取全量候选、追加预审报告、创建混合候选、通知 PO | 不能正式化、修改已有候选、调度 Task Agent |
| TaskNode Owner / 研究员 | 审阅执行草稿并提交候选 | 不能批准正式版本 |
| Project Owner | 影响预览、候选审核、正式化、根任务派发 | 不能代替 Centre Agent 的预审职责 |
| Coordinator | 读取正式快照、维护 PendingHandoff、发布交接或人工通知 | 不改 Mapping、不启动 Worker、不创建执行记录 |
| Registry | 登记主体、Agent、联系人事实 | 不授权、不决定执行资格 |
| email-service | 解析联系人并发送人工通知 | 不消费 Redpanda、不把邮件当治理决定 |
| Dashboard | 聚合 Mapping、Wiki、Queue、Gateway 来源并只读展示 | 不写领域或执行状态 |

## 权限与留痕

领域管理 MCP 通过 Bearer 令牌识别调用者，再按能力档鉴权。调用者身份不由请求体中的角色字段决定。对外接口层记录调用方、工具、目标、结果和耗时；领域服务另行记录治理变更。

Centre Agent 的预审报告是正式化前的硬门禁，但预审结论不等于 PO 的正式发布决定。邮件只表示需要人工查看或继续配置，不承载批准、候选选择、正式发布和执行指令。

## 消息与事实归属

- Research Mapping：TaskNode、DependencyEdge、正式版本、`executor_refs`。
- Registry：Principal、Workflow Agent、Agent instance 的登记信息。
- Redpanda：事件排队、offset 和消费过程。
- Coordinator：PendingHandoff、HandoffDispatch 和派发状态。
- Gateway：ExecutionRecord、Worker Lease 和执行处置状态。
- Draft Buffer：领域草稿及其固定审核 Commit。

## 相关页面

- [[concepts/core-flow]]
- [[concepts/deployment-and-operations]]
- [[syntheses/status-and-risks]]
