---
id: ai4-yvh2
status: closed
deps: []
links: [ai4-z3z4, ai4-m0vt, ai4-wd5l, ai4-dhpv]
created: 2026-10-19T15:25:21Z
type: grilling
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# 执行与接纳状态机融合及 Owner 审核工具边界

## Question

端侧执行闭环需要将 Worker 执行、暂停恢复、Owner 审核、返修和两类触发来源统一为一个可实现、可审计的状态模型与 MCP 契约。

## Acceptance Criteria

形成单一 Execution 状态机清单，覆盖命令接收、Worker 执行、暂停等待、失败、取消、结果接纳、返修、驳回和人工接管；明确每个状态由哪个对象承载、由哪个 MCP 工具驱动迁移、写入哪个存储；明确暂停恢复与「每轮新建 Execution Record」规则的相容方式；给出审核接纳阶段的 MCP 工具契约；说明上游触发与 Owner 触发的记录区分方式。

## Answer

### 进程和触发边界

`Gateway` 归入 `sci-weave/task-agent` 项目组，是常驻控制面；短生命周期 Worker 才是实际执行一次 `fast-agent-mcp` loop 的 Task Agent。Gateway、上游收集器和 Worker 是独立进程角色。

上游收集器只消费已正式发布的上游交接事件，并将可启动请求交给 Gateway；它不得绕过 Gateway 直接创建 Worker。Gateway 是所有 Worker 的唯一启动和串行化裁决者：同一 `task_node_id` 的 Worker 不并发、后续请求排队；不同 TaskNode 可在资源策略允许时并发。

MCP Owner 命令与上游交接队列是两条独立输入路径，均汇入 Gateway。所有必要上游任务尚未正式发布时，`submit_owner_command` 可持久化命令和创建 `ExecutionRecord`，但不能启动 Worker；查询、列表、健康检查及适用的取消仍可调用。上游交接的实际队列实现不属于本阶段 MVP。

### 对象、状态与关系

- `OwnerCommand` 是 `submit_owner_command` 的持久化原始意图，保存任务节点、命令、提交者、幂等键、接收时间和接收结果；查询工具不创建它。
- `ExecutionRecord` 是一次已获接受、可追踪的执行尝试，关联触发它的 `owner_command_id`，但不复制命令原文。它可在 Worker 启动前处于 `queued` 或 `blocked`，此时 `started_at` 为空；启动后保存实际输入摘要及其哈希、会话、开始/结束时间、结果或错误摘要和审计关联。
- `TaskSession` 按 `task_node_id` 持有稳定会话标识。其状态是执行记录的会话投影，不替代 ExecutionRecord 的审计事实。
- `AuditEvent` 追加记录命令接收、排队、状态转换、Worker 生命周期、审核决定、取消和错误摘要。

ExecutionRecord 的对外稳定状态为：

```text
blocked → queued → running
                    ├→ waiting
                    ├→ awaiting_acceptance → accepted
                    │                       ├→ needs_revision
                    │                       ├→ rejected
                    │                       └→ human_takeover
                    ├→ failed
                    └→ cancelled
```

`blocked` 表示必要上游尚未正式发布；条件满足后转为 `queued`。Worker 正常生成可审核结果后直接进入 `awaiting_acceptance`；`succeeded` 不是对外稳定状态，只作为运行时成功退出的审计事实。`accepted` 仅表示 TaskNode Owner 完成对该执行结果的接纳，不代表 Project Owner 的正式发布。

`waiting` 是本次 ExecutionRecord 的终结状态：Worker 因 `PAUSE` 提问后退出。TaskSession 投影为 waiting 并保存待答问题。Owner 回答时创建新 ExecutionRecord，通过 `resume_of` 指向等待记录，不跨进程延续旧 Worker。

`request_revision` 将原记录处置为 `needs_revision`，并生成关联 `revision_of` 的新 ExecutionRecord；重试使用 `retry_of`。`reject` 不自动重试；`request_human_takeover` 将原记录标为 `human_takeover` 并停止自动调度。以上关联保持旧记录不可覆盖、可审计。

### MCP 契约

Gateway 在既有提交、查询、取消、列表和健康检查工具之外，增加：

```text
review_execution
  in:  execution_id: str,
       decision: "accept" | "request_revision" | "reject" | "request_human_takeover",
       reason: str,
       idempotency_key: str
  out: execution_id, decision, execution_status,
       successor_execution_id | null, duplicate: bool
```

相同 `execution_id + idempotency_key` 的重复请求返回首次结果；相同键但内容不同则拒绝并审计。`list_pending` 默认返回 `blocked`、`queued`、`running`、`waiting` 和 `awaiting_acceptance`，并为每项提供 `action_required`：`none`、`answer` 或 `review`。记录保存 `trigger` 与 `trigger_ref`，值可为 `owner_command`、`upstream_handoff` 或 `system_retry`，以区分来源并支持筛选。

`submit_owner_command` 立即返回稳定的 `command_id`、`execution_id` 和当前状态，不等待最终结果；Owner 通过 `query_execution` 获取最终结果或待答问题。邮件仅用于提醒，不承载执行、审核或上游交接事实。

### 领域草稿和原件边界

`review_execution(decision="accept")` 只写入 Gateway SQLite 中的审核决定和 AuditEvent，不自动创建 Research Mapping 或 LLM-Wiki 草稿，也不创建领域 outbox。人控制 Codex 基于已接纳的 ExecutionRecord，经对应领域 MCP 显式提交草稿；该显式提交才是进入领域一审的动作。

PDF 等原件仅以 Wiki 资源卡记录定位、哈希、媒体类型、来源和访问状态；Wiki 不保存原件本体，Codex 对话和 MCP 命令不携带原件二进制内容。若任务确需读取原件，获授权的 Task Agent 可通过独立、受控的资源读取能力按需访问，并把派生摘要、证据或资源卡写回；该资源读取能力不属于 Gateway MVP。

## Notes

**2026-10-20 Revision：** “上游收集器不得绕过 Gateway 直接创建 Worker”中的 Gateway 现明确为 **Task Agent Gateway 组件组**，不是单一进程。`gateway/ingest` 与 `gateway/mcp` 是组件组内的独立子项目；二者均可在共享 SQLite 中为同一 `task_node_id` 原子取得执行租约后启动 `worker` 子项目。它们必须共同遵守组件组的状态机、审计和串行化约束，未取得租约不得启动第二个 Worker。组件组外的队列消费者、收集器或客户端不得启动 Worker。该修订保留“不得绕过 Gateway”的边界，并取代本票中“上游收集器只能交给 Gateway、不得直接创建 Worker”的单进程理解；租约崩溃恢复与上游终态放行规则继续由 [Task Agent 项目组三角色部署与双入口调度边界](ai4-6fb7.md) 收敛。

**2026-10-20 Resolution：** 以上结论由 TaskNode Owner 与本次 Wayfinder 讨论确认。MVP 的调用者身份仍只有本地开发令牌，不能伪装为已完成每个 TaskNode 的 Owner 授权校验；多人身份和授权绑定保留为后续范围。

**2026-10-21T14:13:38Z**

2026-10-21T22:14:00Z

修订说明（本票已关闭，正文保留），依据「Agent 以消息驱动，MCP 只负责返修」(ai4-dhpv)。

作废部分：

- `submit_owner_command` 作为任务下发入口。任务改由消息驱动，首轮由上游交接消息或根任务就绪消息触发。
- `ExecutionRecord.trigger` 取值中的 `owner_command`。改为消息来源，具体取值由新票定义。
- 「MCP Owner 命令与上游交接队列是两条独立输入路径，均汇入 Gateway」中的「MCP Owner 命令」作为**输入路径**的地位。它不再是输入路径，只是人工介入面。

仍然成立：单一 ExecutionRecord 状态机与稳定状态集合；`review_execution` 的四种决定与幂等语义；`list_pending` 的排序与 `action_required` 取值；`query_execution` 返回待答问题；AuditEvent 形状；同一 TaskNode 串行、跨 TaskNode 并发；接纳不自动创建领域草稿。

**2026-10-21T14:34:22Z**

2026-10-21T22:37:00Z

更正上一条（2026-10-21T22:14:00Z）：把 `submit_owner_command` 整体列为「作废部分」措辞过宽。

准确表述：

- 该工具保留，用途从「任务输入路径」收窄为「返修与处置要求入口」。
- 任务下发改走消息队列，因此它不再是与上游交接并列的**任务输入路径**。
- `ExecutionRecord.trigger` 中 `owner_command` 的语义随之改变：它表示「由人工处置要求触发」，不再表示「由任务命令触发」。

依据：「Agent 以消息驱动，Gateway 的 MCP 只负责返修」(ai4-dhpv) 的 2026-10-21T22:35:00Z 澄清。

**2026-10-22T12:23:45Z**

2026-10-22 再修订（本票已关闭，正文与 2026-10-21「工具保留、trigger 改为人工处置」更正均保留）。

推翻 2026-10-21T22:37:00Z 的更正，以及「仍然成立」里已被规格删掉的部分：

- `submit_owner_command` 删除，不存在「人工处置要求入口」这个工具。
- `trigger` 只有队列来源，不再有 `owner_command`。
- 删除 `blocked`、`awaiting_acceptance`、`accepted`。`review_execution` 只有 request_revision、reject、request_human_takeover。
- 正常终点是 completed 并保存 draft_id。草稿由 Worker 内的 agent 写入，不是「接纳后再由人另写」。

依据：「Agent 以消息驱动，Gateway 的 MCP 只负责返修」(ai4-dhpv) 的 Resolution，以及「最小 Work Agent 实现规格」(ai4-z3z4)。

仍然成立：单一 ExecutionRecord 状态机；同一 TaskNode 串行、跨 TaskNode 并发；AuditEvent 只追加。
