---
id: ai4-p5f3
status: open
deps: []
links: []
created: 2026-10-23T11:28:01Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-te1v
tags: [wayfinder:grilling, centre-control, message-queue, handoff]
---
# 交接协调服务的职责、存储边界与 centre-control 部署形态

明确消息队列中 dependency-notice 的主消费者、PendingHandoff 的事实归属、task_handoff_ready 的生成边界，以及交接协调服务在 sci-weave/centre-control 中的独立部署形态。该票不实现服务，只形成可交给实现规划的架构决策。

## Design

需要裁决：

1. 是否新增 `sci-weave/centre-control/handoff-coordinator/` 独立 Python 子项目；
2. 为什么不由 `centre-agents` 或 `research-map` 承担；
3. `dependency-notice` 的消费、重算、幂等和补偿边界；
4. `PendingHandoff` 的存储权威和字段；
5. Research Mapping、Registry、Redpanda、通知服务之间的接口；
6. `executor_refs` 已配置但 Agent 离线、未登记或无实例时的处理；
7. `task_handoff_ready` 与 `human_notification_intent` 的发布条件；
8. 失败、重试、死信、offset 和审计边界。

## 当前决策基线

- `task-workflow`、`centre-workflow`、`email-service` 不是同一种交接消费者，不把它们都建模成 `task_handoff_ready`。
- 当前 Centre Agent 是 `centre-workflow` 的一个预审 Workflow，订阅候选创建、候选头更新和正式版本发布事件；后续中央 Workflow 通过独立订阅声明和消费者组扩展。
- 服务启动恢复采用三层模型：同一消费者组继续消费未提交 offset；扫描未完成的 `PendingHandoff` 和 `HandoffDispatch`；消息过期后依据正式 Mapping 补偿重算。
- `HandoffDispatch` 覆盖“事件发送结果未知”的崩溃窗口，重复发布由 `dedupe_key` 和下游幂等共同保护。
- 详细消息目标类型、Centre Workflow 可扩展订阅和启动恢复流程记录在 [`消息交接恢复与多目标订阅`](../docs/data-flow/message-delivery-recovery.md)。
- 已接受新增独立交接协调服务；`PendingHandoff` 与 `HandoffDispatch` 由该服务的持久化边界负责，Task Agent、Centre Agent 和邮件服务分别只保存自己的执行或投递事实。
- Research Mapping 访问方式尚未收敛，已拆为决策票「Research Mapping 正式快照查询接口与交接协调服务访问边界」；在该接口确定前，交接协调服务不能进入实现规划。
- 启动恢复和 Centre Workflow 可扩展订阅已形成基线；研究员端新建 `task-workflow` 后如何发现和订阅 `task_handoff_ready`，另由「研究员 Task Agent 动态订阅 task-workflow 交接消息」收敛。
- 候选决策不支持 `defer`：PO 必须选择 `formalize`、`request_revision` 或 `reject`。`request_revision` 必须指定唯一 `repair_owner_id`，返修由负责人自己的 Task Agent 完成，Centre Agent 不负责返修。
- 混合候选不可行时，PO 可以指派负责人组织返修，也可以通过高权限 PO MCP 创建新的混合候选；正式版本不可原地修改，Mapping 与 Wiki 仍分别治理。
- 无后续 TaskNode 时发送 `task_terminal_summary` 通知 PO；PO 通过 MCP 创建后续任务/依赖候选，不直接操作队列。
- PO 决策与根任务分派已进一步收敛：不支持 `defer`；`request_revision` 必须指定唯一 `repair_owner_id`；PO 可以指派混合候选返修或直接创建新混合候选；根任务第一条 `task_handoff_ready` 由 PO 通过幂等 `dispatch_root_task` 发送。正式版本当前没有后继时保留待推进检测，确认没有后继后额外发送 `task_terminal_summary` 邮件；后续新后继正式化后自动重算并发送交接消息。详情见「PO 候选裁决、返修指派与根任务分派 MCP」。

## Acceptance Criteria

- 明确交接协调服务是否作为 centre-control 下独立部署角色，以及与 centre-agents、research-map 的边界
- 明确 `task-workflow`、可扩展的 `centre-workflow`、`email-service` 三类目标的事件语义、订阅和消费者组
- 明确 `dependency-notice` 的主消费者、`task_handoff_ready` 的唯一生成者和各目标 topic 的消费关系
- 明确 PendingHandoff 与 HandoffDispatch 的权威存储、生命周期、幂等键和补偿重算触发
- 明确 executor_refs、Registry 登记、Agent 实例可用性三者的关系，不把 Registry 当授权源
- 明确 human_notification_intent/通知服务的接口边界，邮件成功不等于任务完成
- 明确候选决策不支持 `defer`，`request_revision` 必须指定唯一 `repair_owner_id`，Centre Agent 不承担返修
- 明确混合候选不可行、PO 直接创建新混合候选、Mapping/Wiki 独立治理和无后续 TaskNode 通知 PO 的流程
- 明确 PO 高权限 MCP 不直接操作队列或领域存储，根任务通过幂等分派工具生成任务交接
- 明确正式版本当前无后继时先保存待推进检测，确认无后继后通知 PO；后续新后继正式化后自动生成任务交接
- 明确队列基础设施失败、非法消息、领域条件不满足、派发结果未知和 Worker 业务失败的不同处置
- 明确服务启动恢复未提交 offset、未完成协调记录和消息过期补偿扫描三层边界
- 形成可供实现票引用的部署、配置、依赖和验证边界

## Not yet specified

- [Research Mapping 正式快照查询接口与交接协调服务访问边界](ai4-2982)：交接协调服务如何通过稳定领域接口读取一致的正式 Mapping 快照，仍需裁决传输方式和访问契约。
- [研究员 Task Agent 动态订阅 task-workflow 交接消息](ai4-nfty)：研究员创建新 Workflow 后，端侧如何发现正式 `executor_refs` 并恢复任务交接订阅。
- [PO 候选裁决、返修指派与根任务分派 MCP](ai4-9mf8)：收口 PO 高权限决策工具、混合候选返修负责人和无上游根任务分派边界。

## Notes

**2026-10-23**：本轮进一步收敛候选和通知边界：取消 `defer`；PO 的候选决策只能是 `formalize`、`request_revision` 或 `reject`。返修必须指定唯一 `repair_owner_id`，由负责人自己的 Task Agent 执行；Centre Agent 只预审，不返修。混合候选不可行时，PO 可以指派负责人组织返修或通过高权限 MCP 创建新混合候选。无后续 TaskNode 时发送 `task_terminal_summary` 通知 PO，PO 通过 MCP 创建后续候选，不直接操作队列。相关 PO 工具边界另见「PO 候选裁决、返修指派与根任务分派 MCP」。
