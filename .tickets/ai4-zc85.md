---
id: ai4-zc85
status: closed
deps: []
links: []
created: 2026-10-23T14:07:18Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-p5f3
tags: [wayfinder:grilling, centre-control, coordinator, handoff, message-queue]
---
# handoff coordinator 依赖重算与派发恢复规格

先于 coordinator 实现，明确正式 Mapping 事件输入、原子快照查询端口、PendingHandoff/HandoffDispatch 状态、任务交接与人工通知输出、无后继检测和启动恢复边界。Research Mapping MCP 访问传输已由 ai4-2982 的 `get_formal_mapping_at_revision` 契约定案：交接协调服务经 research-map 管理 MCP（Streamable HTTP）读取正式快照，不得直连 SQLite/TerminusDB。

## Design

只形成服务规格，不写代码。协调服务的职责边界继承 ai4-p5f3 与 ai4-te1v 的决策基线：`dependency-notice` 的主消费者是交接协调服务，统一生成 `task_handoff_ready`；它只做依赖重算、交接等待、派发与恢复，不创建 Task Agent 的 ExecutionRecord，不修改正式 Map，不裁决执行结果。

### 输入端口

协调服务有且只有两类输入，都通过可替换端口注入（首版以 Fake 端口验证，真实 Redpanda 适配器待 ai4-te1v 消息语义收敛后接入）：

1. **formal_revision_published 事件**：载荷只带 `mapping_domain_id` 与 `formal_revision_id`（领域标识），不带正文；由正式版本发布时领域 MCP 经治理事件发布。触发对该版本的**结构重算**：加载正式快照、判定后继、维护 PendingHandoff。
2. **task_completed 事件**：载荷带 `mapping_domain_id`、`task_node_id`、完成的 `version_ref`。触发依赖重算：以上游节点已完成事实重新判定依赖边的执行条件。首版不依赖特定消息产品，事件经 `FormalEventPort`/`TaskEventPort` 传入。

### 正式快照查询端口

- 按 `get_formal_mapping_at_revision(mapping_domain_id, formal_revision_id)` 读取保持一致性的最小依赖图（TaskNode / DependencyEdge / `executor_refs` / 版本引用）。
- 错误语义按 ai4-2982：`unavailable` 退避重试；`inconsistent` 与 `no_such_revision` 视为不可恢复，记录失败事实并转人工，不自行降级。
- 协调服务只从该端口获得拓扑与执行者关系；后继判断、依赖输出、`executor_refs` 与终点判定一律基于该端口返回的正式快照。

### PendingHandoff 与 HandoffDispatch

两者都是协调服务自己的 SQLite 状态库（`SCIWEAVE_COORDINATOR_SQLITE_PATH`），与领域库物理隔离。用 JSON 文本列表达可选细粒度字段，不复制领域正文。

**PendingHandoff** 表示「目标 TaskNode 的一次交接等待事实」，幂等键为 `(mapping_domain_id, task_node_id, target_node_version_ref)` 唯一约束：

- 字段：`pending_handoff_id`、`mapping_domain_id`、`task_node_id`、`target_node_version_ref`、`upstream_source_refs`（JSON，入边来源节点与版本）、`executor_agent_id`（来自 `executor_refs`）、`status`、`created_at`、`updated_at`、`last_trigger_revision_id`。
- 状态机：`waiting`（条件未满足）→ `ready`（条件满足，等待派发）→ `dispatched_unknown`（已派发但结果未知）→ `done`（确认投递）；任一等待态可被 `superseded`（目标版本移动，追加新记录而非原地改）或 `failed`（不可恢复，如快照 `inconsistent`/`no_such_revision`）。
- 一个 `task_node_id` 的旧版等待事实被替代时不删除，追加 `superseded` 新记录，与 ai4-oz3s 的「追加判定」同风格。

**HandoffDispatch** 表示一次消息发布尝试，幂等键为 `dedupe_key = mapping_domain_id + task_node_id + target_node_version_ref + trigger_revision_id` 唯一约束：

- 字段：`dispatch_id`、`pending_handoff_id`、`dedupe_key`、`message_type`（`task_handoff_ready` / `human_notification_intent` / `task_terminal_summary`）、`target_agent_id`、`status`、`attempt_count`、`error_summary`、`created_at`、`updated_at`。
- 状态：`created` → `published`（发布成功）→ `result_unknown`（发布后进程崩溃，处理结果未知）→ `failed`（可重试）/ `dead`（死信）。重复发布由 `dedupe_key` 唯一约束与下游幂等共同保护。
- `attempt_count` 参与重试上限与退避；达到上限未确认进入 `dead`，人工可经运维查询处理，不自动重放。

### 输出条件

- **task_handoff_ready**（目标节点交接消息）：目标节点已正式化、其全部依赖边来源「正式化齐备」且「执行完成事实齐备」、执行者 `executor_refs` 可定位。按 `sciweave.task-handoff.<agent_id>` 路由，载荷必须携带 `target_agent_id`、`target_node_version_ref`、`mapping_domain_id`、`pending_handoff_id` 与 `trigger_revision_id`，使下游可校验正式执行关系。
- **human_notification_intent**：结构上无法推进或执行者不可达时走人工路径，经 email-service 的 `send_notification` 投递，不改正式 Map。场景包括：快照 `inconsistent`/`no_such_revision`、执行者未登记且无法定位 topic、流程进入死信。载荷引用目标节点/版本与原因摘要。
- **task_terminal_summary**：确认当前正式版本中某个 TaskNode 没有任何后继节点时，向 PO 发送终点汇总通知；后续有新后继 TaskNode 或 DependencyEdge 正式发布时，重新重算并自动发送对应 `task_handoff_ready`，不要求 PO 再次手工触发。

### 差异判定（用例级）

| 情形 | 判定 | 处置 |
| --- | --- | --- |
| 无后继 | 快照中目标无出边 | 保存终止事实，发 `task_terminal_summary` 给 PO |
| 条件未满足 | 入边来源未全部具备正式化/执行完成事实 | PendingHandoff 保持 `waiting`，后续事件重算 |
| Agent 不可用 | 执行者未登记/注销且无实例 | 不改正式 Map，发 `human_notification_intent`，等待事实保留 |
| 查询失败 | `unavailable` | 退避重试、保持 `waiting`、可观测 |
| 查询不可恢复 | `inconsistent`/`no_such_revision` | 记录 `failed` 并转人工，不降级不重放 |
| 派发结果未知 | 发布后无确认 | HandoffDispatch 置 `result_unknown`，启动扫描按幂等键复查 |
| 重复输入 | 同一事件/同一重算再次到达 | `dedupe_key` 唯一约束去重，不重复发布 |

### 启动恢复、补偿、重试与死信

- 三层恢复（继承 ai4-p5f3/ai4-te1v）：同一消费者组续消费未提交 offset；扫描未完成 `PendingHandoff`/`HandoffDispatch`；消息过期后依据正式 Mapping 做补偿重算。
- 补偿扫描：启动时读取全部非终态记录，按其事务重新取正式快照判定；`formal_revision_published` 事件本身也可能过期，靠补偿扫描兜底。
- 重试：`unavailable` 与 `failed`（可重试）按退避重试；`dead` 不再自动重放。
- 死信：记录 `dead` 与原因，可查、可人工处置；不产生活消息污染。

### 不修改正式 Map

- 协调服务只经查询端口读取正式 Mapping，仅写自己的状态库与输出消息。
- 任何失败都不回写、不降级、不把版本名改成其他版本重放；对领域的事实异议走人工路径。

## Acceptance Criteria

- [x] 明确 formal_revision_published/task_completed 输入与正式快照查询端口（`get_formal_mapping_at_revision`）的契约与错误重试语义
- [x] 明确 PendingHandoff/HandoffDispatch 最小 schema、状态迁移和幂等键
- [x] 明确 task_handoff_ready、human_notification_intent、task_terminal_summary 输出条件与载荷
- [x] 明确无后继、条件未满足、Agent 不可用、查询失败和派发结果未知的区别
- [x] 明确启动恢复、补偿扫描、重试、死信和不修改正式 Map 边界
- [x] 形成可供 coordinator 实现票引用的接口与验证契约

## Notes

**2026-10-25 规格收敛（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

规格正文从「只形成服务规格」一句话扩展为上方契约：输入端口两类事件、查询端口复用 ai4-2982 的 `get_formal_mapping_at_revision`、PendingHandoff/HandoffDispatch 的 schema 与状态机、三类输出、七种差异判定的用例表、三层恢复与不修改正式 Map。审核时对照 ai4-p5f3（职责与部署形态）、ai4-te1v（消息协作基线）、ai4-2982（查询契约）、ai4-1y6q（实现票验收）逐项对齐；`task_handoff_ready` 载荷字段与 ai4-nfty 的订阅校验要求一致（`target_agent_id` + `target_node_version_ref`）。

**2026-10-25T06:58:36Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T06:58:36Z。
