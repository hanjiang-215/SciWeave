---
id: ai4-z3z4
status: open
deps: [ai4-yvh2]
links: [ai4-yyy9]
created: 2026-10-19T07:07:36Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [spec, gateway, fast-agent]
---
# Gateway MVP 与最小 fast-agent 技术规格

将 Gateway 与最小 fast-agent 执行闭环的 Wayfinder 决策整理为可实现的技术规格。该规格是实现 tickets 的唯一上游输入，不包含 Research Mapping MCP、Agent Kit 或 ZIP 交付。

## Design

## Problem Statement
仓库已有 fast-agent-mcp 外部 Worker 启动、固定会话恢复和端侧 Gateway 边界决策，但尚无产品代码入口。需要建立最小 Gateway，使 Owner 能提交受控命令，平台能持久化执行状态并按需启动短生命周期 Worker，完成一次 fast-agent loop。

## Solution
实现一个 Python 常驻 Gateway：以 **MCP（Streamable HTTP）** 作为 Owner 请求入口，使用 SQLite 保存 TaskSession、OwnerCommand、ExecutionRecord 和 AuditEvent，使用本地进程调度器按 `task_node_id` 串行启动 Worker，使用 Runtime Adapter 调用 fast-agent-mcp。Worker 使用平台生成的固定 `session_id`、专属持久 home、connection scope 和 session history；每次 loop 完成或暂停后退出。

Gateway 是 MCP server，Task Owner 的 Codex 是 MCP client，仅通过 `mcp_servers` 注册地址与令牌。不采用 stdio 传输，因为 Codex 会自行 spawn 进程并随会话退出，破坏 Gateway 常驻、持久化调度状态与跨会话串行调度。

Task Agent 项目组的三角色目录、双入口原子租约与具体崩溃恢复规则由 [Task Agent 项目组三角色部署与双入口调度边界](ai4-6fb7.md) 单独收敛；本规格不预设尚未完成的目录迁移实现。

## Public seams
Gateway 通过 MCP 工具对外暴露以下能力：

- `submit_owner_command`：提交 `task_node_id`、命令内容和幂等键，立即返回稳定的 `command_id`、`execution_id` 和当前状态；必要上游尚未正式发布时可创建 `blocked` 执行，但不启动 Worker。
- `query_execution`：按 `execution_id` 查询当前状态、结果摘要、错误摘要、会话标识，以及 `waiting` 时的待回答问题。
- `cancel_execution`：按 `execution_id` 请求取消；已终结执行返回不可取消。
- `list_pending`：列出需要继续跟进的执行，供 Owner 恢复上下文。
- `review_execution`：接纳、要求返修、驳回或请求人工接管可审核结果。
- `health`：返回 Gateway 聚合健康状态及其 MCP、消息队列分项状态。

MCP server 的传输地址、端口和令牌全部由环境变量提供。回环 HTTP 健康端点与 MCP `health` 共用同一份健康计算逻辑，仅用于本地探测、调试和测试，不是 Owner 主通道。

### MCP 工具契约

工具名使用动词_名词形式，参数与返回均为 JSON 对象；所有错误通过工具的 `isError` 标记与结构化 `error` 字段返回，不抛传输层异常。

```text
submit_owner_command
  in:  task_node_id: str, command: str, idempotency_key: str,
       execution_id: str | null
  out: command_id, execution_id, task_node_id, session_id,
       command_status, execution_status, duplicate: bool
  规则: idempotency_key 唯一；相同键返回既有执行且 duplicate=true；
       execution_id 非空时只用于 waiting 后的回答，创建带 resume_of 的新
       ExecutionRecord，不跨进程恢复旧 Worker。

query_execution
  in:  execution_id: str
  out: execution_id, task_node_id, session_id, execution_status,
       result_summary: str | null, error_summary: str | null,
       pending_question: str | null, trigger, trigger_ref
  规则: 不存在返回 isError 与 error=not_found；
       execution_status=waiting 时 pending_question 必填。

cancel_execution
  in:  execution_id: str
  out: execution_id, execution_status, accepted: bool
  规则: 已终结执行返回 accepted=false 与 error=not_cancellable。

list_pending
  in:  task_node_id: str | null
  out: executions: [{execution_id, task_node_id, execution_status, created_at,
                     action_required, trigger, trigger_ref}]
  规则: 默认返回 blocked、queued、running、waiting、awaiting_acceptance；
       action_required 为 none、answer 或 review。

review_execution
  in:  execution_id: str,
       decision: "accept" | "request_revision" | "reject" |
                 "request_human_takeover",
       reason: str, idempotency_key: str
  out: execution_id, decision, execution_status,
       successor_execution_id | null, duplicate: bool
  规则: 相同 execution_id + idempotency_key 的重复请求返回首次结果；
       相同键但内容不同则拒绝并审计。request_revision 创建带 revision_of
       的新记录；reject 不自动重试；request_human_takeover 停止自动调度。

health
  in:  (无)
  out: status: "ready" | "degraded" | "unavailable",
       gateway: {status, storage, scheduler},
       mcp: {status, listener, authentication},
       message_queue: {status, consumer, last_confirmed_at, backlog},
       worker_runtime: {status}
  规则: MCP 与消息队列分别汇报；消息队列未配置时明确返回 not_configured。
       Gateway 无法安全持久化或调度时为 unavailable；可选依赖异常但 Gateway
       仍可持久化 Owner 命令时为 degraded。
```

## Domain objects and state

- TaskSession：每个 `task_node_id` 一个稳定 `session_id`；其状态是执行记录的会话投影，不替代 ExecutionRecord 的审计事实。
- OwnerCommand：`submit_owner_command` 的持久化原始意图，保存任务节点、命令、提交者、幂等键、接收时间和接收结果；查询工具不创建它。
- ExecutionRecord：一次可追踪的执行尝试，关联触发它的 OwnerCommand。Worker 启动前可处于 `blocked` 或 `queued`，且 `started_at` 为空；启动后保存实际输入摘要与哈希、会话、起止时间、结果或错误摘要和审计关联。暂停、返修和重试均创建新记录，分别以 `resume_of`、`revision_of`、`retry_of` 关联旧记录。
- AuditEvent：追加记录命令接收、排队、状态迁移、Worker 创建/退出、运行时结果、审核决定、取消和错误摘要。

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

`blocked` 表示必要上游尚未正式发布；条件满足后转为 `queued`。Worker 正常生成可审核结果后直接进入 `awaiting_acceptance`。`succeeded` 只作为运行时成功退出的 AuditEvent/运行时事实，不是对外稳定状态。`waiting` 终结本轮 ExecutionRecord；Owner 回答时创建带 `resume_of` 的新记录。记录以 `trigger` 与 `trigger_ref` 区分 `owner_command`、`upstream_handoff` 与 `system_retry`。

## Runtime and persistence
Gateway 核心只依赖 Runtime Adapter、Execution Store 和 Worker Scheduler。首版适配器分别为 fast-agent Runtime Adapter、SQLite Store 和本地进程 Scheduler。Gateway 在一个 SQLite 事务中创建 OwnerCommand、ExecutionRecord 初始记录和命令审计事件；条件满足后调度 Worker。重复幂等键返回既有命令及其结果，不创建新的执行。

Runtime Adapter 至少支持 run、resume 和 cancel；同一 `task_node_id` 不能同时有两个 Worker。Worker 以固定 `session_id` 恢复 fast-agent Harness，会话 home 必须持久化，默认关闭自动 compaction。运行时异常、超时、非零退出或会话无法恢复时，ExecutionRecord 进入 `failed` 并保存不含凭据的错误摘要；Gateway 重启不自动重做已失败执行。

`review_execution(decision="accept")` 只写入 Gateway SQLite 中的审核决定与 AuditEvent，不自动创建 Research Mapping 或 LLM-Wiki 草稿，也不创建领域 outbox。人控制 Codex 基于已接纳的 ExecutionRecord，经对应领域 MCP 显式提交草稿；该显式操作才进入领域一审。正式交付内容的领域 Buffer 不属于本规格。

## Authentication and configuration
首版只支持本地开发令牌配置；真实令牌通过环境变量或本机安全配置注入，不能写入仓库。首版不实现多人身份与 TaskNode Owner 授权绑定、跨网络 MCP、Redpanda、EventBus 或领域 MCP。

## Testing decisions
测试通过 MCP 工具公共 seam 验证外部行为，不检查私有实现。必须覆盖：健康检查、首次命令提交、幂等重复提交、`blocked` 执行查询、执行状态查询、Worker 成功进入 `awaiting_acceptance`、运行时失败、取消、同一 `task_node_id` 串行化、`waiting` 后创建 `resume_of` 新记录、审核决定、Gateway 重启后的会话恢复，以及使用 passthrough fast-agent 的最小运行时集成测试。真实模型凭据不进入测试。

## Out of scope
Research Mapping MCP、依赖图、领域 Buffer 设计、Agent Kit/Skills/Hooks、ZIP 交付、跨服务器部署、Redpanda 消息队列具体实现、A2A 传输、真实模型提供商接入和生产级自动恢复。

## Acceptance Criteria

- [ ] MCP 工具接口、对象状态和 SQLite 持久化规则明确且可实现。
- [ ] 一次 Owner Command 能产生可查询的 ExecutionRecord 和 AuditEvent，并在上游未就绪时保留为 `blocked`。
- [ ] 相同幂等键不会创建第二个执行；暂停、返修和重试会创建关联的新 ExecutionRecord。
- [ ] Worker 能通过 fast-agent Runtime Adapter 完成一次 loop 并释放；同一 `task_node_id` 串行化。
- [ ] `review_execution` 可审计地接纳、返修、驳回或人工接管，且接纳不产生领域草稿或 outbox。
- [ ] 固定 `session_id` 能在新的 Worker 中恢复；失败、取消、审核、串行化和 Gateway 重启读取行为有自动化验证。
- [ ] 同一健康计算逻辑分别报告 MCP 与消息队列状态，不将未配置队列伪装为可用。
- [ ] 规格未引入领域对象正文、领域 MCP 逻辑、Agent Kit 或 ZIP 交付。

## Notes

**2026-10-19T08:53:34Z**

关联 Gitee Pull Request #9：https://gitee.com/qi-yueran/ai4science/pulls/9（目标 develop）。PR 包含 Gateway MVP 基础闭环、技术栈约束与实现路线图；后续实现票仍按依赖图推进。

**2026-10-19T20:12:00Z**

规格修订（2026-10-19）：Owner 通道由 HTTP 自定义端点改为 MCP（Streamable HTTP）。原因：主流 harness（Codex CLI、Cursor、Claude Code）对外扩展面只有 MCP，没有内置 A2A 客户端，Owner 无法直接作为 A2A 客户端接入。

- 保留 HTTP 回环端点，但只承担健康检查、本地调试和测试 seam，不再是 Owner 主通道。
- 不使用 stdio 传输：Codex 会自行 spawn 进程并随会话退出，破坏 Gateway 常驻、SQLite 单写者和跨会话串行调度。

**2026-10-20T04:07:00Z**

状态机与契约修订：本规格已与 [执行与接纳状态机融合及 Owner 审核工具边界](ai4-yvh2.md) 对齐，采用稳定执行状态、`review_execution` 和关联的新 ExecutionRecord；健康契约同时分项报告 MCP 与消息队列。Task Agent 项目组三角色与双入口调度细节仍由 [Task Agent 项目组三角色部署与双入口调度边界](ai4-6fb7.md) 收敛。