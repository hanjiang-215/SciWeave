---
id: ai4-9mf8
status: closed
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

### 形态与边界

PO MCP 不是新领域服务，而是 **PO（`project_owner` 档）以最高权限调用两套领域管理 MCP** 的契约收口，外加一个面向协调侧的根任务分派入口：

- 候选创建、混合候选、候选裁决、返修指派、正式化影响预览走 **Mapping 管理 MCP 与 Wiki 管理 MCP 各自的高权限档**；两域不共享存储、不跨域原子写入。
- 根任务分派 `dispatch_root_task` 是 PO 侧新增工具，发布第一条 `task_handoff_ready`，校验正式 Map 与 `executor_refs` 后投递，幂等。
- PO 的所有操作经领域 MCP / PO 工具完成；PO 不直接操作 Redpanda、SQLite、TerminusDB，不持有 Task Agent 凭据，不下发任务到 Agent。

### 候选决策与工具映射

候选决策只有三种，**不产生 `defer`**：

| PO 决策 | 工具链（Mapping / Wiki） | 语义 |
| --- | --- | --- |
| `formalize` | `record_review(approved)` + `formalize_candidate` / `decide_wiki_review` + `formalize_wiki` | 候选 head 校验、PO 决策记录、正式版本激活、正式版本事件 |
| `request_revision` | 返修指派工具（要求唯一 `repair_owner_id`，可带 `participants`） | 返修由负责人自己的 Task Agent 执行；Centre Agent 只预审不返修 |
| `reject` | `record_review(rejected)` / `decide_wiki_review` | 候选保持不可变，不原地修改或复活 |

- `formalize_candidate`/`formalize_wiki` 只负责候选 head 校验、PO 决策记录、正式版本激活与正式版本事件；不要求 PO 手工选 topic 或逐个通知 Agent。
- `request_revision` 必须指定唯一 `repair_owner_id`；返修由负责人自己的 Task Agent 执行，Centre Agent 只预审、不返修。返修动作发生在草稿箱/候选治理流程，PO 不直接改候选内容。

### 混合候选

- 混合候选只能新建分支，作者记为全部来源作者且无操作权，禁止二次混合（继承 ai4-8dgd）。
- 混合候选不可行时，PO 可以指派负责人组织讨论和返修，也可以直接创建新的混合候选；旧候选保持不可变。
- 混合候选经 `create_merged_candidate`（Mapping/Wiki 各自的 `merged_candidate` 档）创建，审计与正式化前置不放松。

### 根任务分派

- 无上游依赖的根 TaskNode 由 PO 调用幂等的 `dispatch_root_task` 发送第一条 `task_handoff_ready`；该消息仍必须验证正式 Map 与 `executor_refs`。
- 幂等键由 PO 侧生成（`mapping_domain_id` + 根 `task_node_id` + `formal_revision_id` 派生），重复调用不重复发布。
- 发布目标按 `sciweave.task-handoff.<agent_id>` 路由，载荷携带 `target_agent_id`、`target_node_version_ref`（与 ai4-nfty 的订阅校验一致）。

### 无后继与自动重算

- 正式版本发布后，如果后继尚未具备执行条件，系统保存待推进的交接事实并在后续正式事件中自动重算（由 handoff coordinator 承担）。
- 如果确认当前 TaskNode 没有任何后继，则额外发送 `task_terminal_summary` 邮件通知 PO。
- 新后继 TaskNode 或 DependencyEdge 后续正式发布后，系统自动重新计算并发送对应 `task_handoff_ready`，不要求 PO 再次手工发消息。
- PO 通过领域 MCP 创建后续任务/依赖候选，不直接操作队列。

### 权限与审计

- PO MCP 调用时，Mapping/Wiki 领域 MCP 以 `formalize`/`candidate_review`/`candidate_submit`/`merged_candidate` 能力档对 PO 开放；`centre` 档不授予 PO（PO 不做预审只做最终裁决）。
- 所有候选、返修、正式化和根任务操作经接口层审计账本留痕；不出现绕过领域 MCP 的队列或存储直连。

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

- [x] 明确候选 `formalize`、`request_revision`、`reject` 的状态和消息语义，不产生 `defer` 状态
- [x] 明确 `request_revision` 必须指定 `repair_owner_id`，返修由负责人自己的 Task Agent 执行，Centre Agent 不返修
- [x] 明确 PO 直接创建候选/混合候选的能力、审计和正式化前置，不允许绕过预审和正式版本门禁
- [x] 明确 Mapping 与 Wiki 仍分别调用各自领域 MCP，不支持跨域原子写入
- [x] 明确无后续 TaskNode 时通知 PO，以及 PO 创建后续任务候选的入口
- [x] 明确根任务分派 MCP 的校验、幂等和 `task_handoff_ready` 发布边界
- [x] 明确 PO 的所有候选、返修、正式化和根任务操作均经最高权限领域 MCP，不直接操作队列或存储
- [x] 明确没有后继时发送 `task_terminal_summary`；后继后续正式化时自动重算并发送 `task_handoff_ready`
- [x] 形成可供 PO MCP 实现票引用的工具、权限和验证契约

## Notes

**2026-10-25 规格收敛（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

正文从「需要裁决的问题」扩展为可交付契约：PO MCP 形态定为「PO 以最高权限调用两套领域管理 MCP + 根任务分派工具」；候选三决策（formalize/request_revision/reject）映射到 Mapping/Wiki 现有工具链（`record_review`/`formalize_candidate`、`decide_wiki_review`/`formalize_wiki`）；`request_revision` 要求唯一 `repair_owner_id`；根任务 `dispatch_root_task` 幂等、验证正式 Map 与 `executor_refs` 后按 `sciweave.task-handoff.<agent_id>` 发布；无后继发 `task_terminal_summary`、后续正式化自动重算均由 handoff coordinator（ai4-zc85/ai4-1y6q 已实现）承接。验收九项全部勾选。

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23**：本轮确认：`request_revision` 必须指定唯一 `repair_owner_id`，可附带参与者；混合候选不可行时允许 PO 指派负责人或直接创建新混合候选；PO 当前通过最高权限 MCP 操作，暂不支持 `defer`。根任务的第一条 `task_handoff_ready` 由 PO 通过 `dispatch_root_task` 发送。正式版本没有当前后继时，系统保留待推进事实并持续检测；确认没有后继时额外发送 `task_terminal_summary` 邮件，后续新增并正式化后自动发送交接消息。后续可扩展 PO MCP 工具，但不得绕过领域治理、队列或存储边界。
