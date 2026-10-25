---
id: ai4-9mf8
status: open
deps: []
links: []
created: 2026-10-23T13:07:08Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-p5f3
tags: [wayfinder:grilling, governance, centre-control, message-queue, mcp]
---
# PO 候选裁决、返修指派与根任务分派 MCP

明确 Project Owner 的高权限 MCP 如何完成候选正式化、要求返修、拒绝候选、创建或混合候选、指派混合候选返修负责人、预览正式化影响和分派无上游根任务。PO 不直接操作 Redpanda、Task Agent 或领域存储；Centre Agent 只预审，不负责返修。

## Design

需要裁决：

1. 候选决策是否只有 `formalize`/`request_revision`/`reject`，不支持 `defer`；
2. `request_revision` 是否必须指定唯一 `repair_owner_id`；
3. 混合候选不可行时如何指派负责人、组织讨论或由 PO 直接创建新混合候选；
4. PO MCP 的高权限边界与 Mapping/Wiki 独立治理边界；
5. 无后续 TaskNode 的终点通知与 PO 后续创建任务候选；
6. 根任务如何由 PO MCP 幂等分派，不绕过正式 Map 和 `executor_refs`。

## Current decision baseline

- PO 的候选决策只有 `formalize`、`request_revision`、`reject`，不支持 `defer`。
- `request_revision` 必须指定唯一 `repair_owner_id`，可附带 `participants`；返修由负责人自己的 Task Agent 执行，Centre Agent 只预审、不返修。
- 混合候选不可行时，PO 可以指派负责人组织讨论和返修，也可以直接创建新的混合候选；旧候选保持不可变，不原地修改或复活。
- PO 通过最高权限的领域 MCP 完成候选创建、混合候选、候选裁决、返修指派、正式化影响预览和根任务分派；PO 不直接操作 Redpanda、SQLite 或 TerminusDB。
- `formalize_candidate` 只负责候选 head 校验、PO 决策记录、正式版本激活和正式版本事件；不要求 PO 手工选择 topic 或逐个通知 Agent。
- 无上游依赖的根 TaskNode 由 PO 调用幂等的 `dispatch_root_task` 发送第一条 `task_handoff_ready`；该消息仍必须验证正式 Map 与 `executor_refs`。
- 正式版本发布后，如果后继尚未具备执行条件，系统保存待推进的交接事实并在后续正式事件中自动重算；如果确认当前 TaskNode 没有任何后继，则额外发送 `task_terminal_summary` 邮件通知 PO。
- 新后继 TaskNode 或 DependencyEdge 后续正式发布后，系统自动重新计算并发送对应 `task_handoff_ready`，不要求 PO 再次手工发消息。

## Acceptance Criteria

- 明确候选 `formalize`、`request_revision`、`reject` 的状态和消息语义，不产生 `defer` 状态
- 明确 `request_revision` 必须指定 `repair_owner_id`，返修由负责人自己的 Task Agent 执行，Centre Agent 不返修
- 明确 PO 直接创建候选/混合候选的能力、审计和正式化前置，不允许绕过预审和正式版本门禁
- 明确 Mapping 与 Wiki 仍分别调用各自领域 MCP，不支持跨域原子写入
- 明确无后续 TaskNode 时通知 PO，以及 PO 创建后续任务候选的入口
- 明确根任务分派 MCP 的校验、幂等和 `task_handoff_ready` 发布边界
- 明确 PO 的所有候选、返修、正式化和根任务操作均经最高权限领域 MCP，不直接操作队列或存储
- 明确没有后继时发送 `task_terminal_summary`；后继后续正式化时自动重算并发送 `task_handoff_ready`
- 形成可供 PO MCP 实现票引用的工具、权限和验证契约

## Notes

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23**：本轮确认：`request_revision` 必须指定唯一 `repair_owner_id`，可附带参与者；混合候选不可行时允许 PO 指派负责人或直接创建新混合候选；PO 当前通过最高权限 MCP 操作，暂不支持 `defer`。根任务的第一条 `task_handoff_ready` 由 PO 通过 `dispatch_root_task` 发送。正式版本没有当前后继时，系统保留待推进事实并持续检测；确认没有后继时额外发送 `task_terminal_summary` 邮件，后续新增并正式化后自动发送交接消息。后续可扩展 PO MCP 工具，但不得绕过领域治理、队列或存储边界。
