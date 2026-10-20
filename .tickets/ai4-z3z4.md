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
实现一个 Python 常驻 Gateway：以 **MCP（Streamable HTTP）** 作为 Owner 请求入口，使用 SQLite 保存 TaskSession、OwnerCommand、ExecutionRecord 和 AuditEvent，使用本地进程调度器按 task_node_id 串行启动 Worker，使用 Runtime Adapter 调用 fast-agent-mcp。Worker 使用平台生成的固定 session_id、专属持久 home、connection scope 和 session history；执行完成后保存结果并退出。

Gateway 是 MCP server，Task Owner 的 Codex 是 MCP client，仅通过 `mcp_servers` 注册地址与令牌。不采用 stdio 传输，因为 Codex 会自行 spawn 进程并随会话退出，破坏 Gateway 常驻、SQLite 单写者和跨会话串行调度。

## Public seams
Gateway 通过 MCP 工具对外暴露以下能力：

- `submit_owner_command`：提交 task_node_id、命令内容和幂等键，返回 command_id、execution_id 和初始状态；带同一 execution_id 提交时视为续接该执行。
- `query_execution`：按 execution_id 查询当前状态、结果摘要、错误摘要、session 标识，以及 `waiting` 时的待回答问题。
- `cancel_execution`：按 execution_id 请求取消；已完成执行返回不可取消。
- `list_pending`：列出未终结的命令与执行，供 Owner 恢复上下文。
- `health`：返回 Gateway 可接受请求和本地存储可用状态。

MCP server 的传输地址、端口和令牌全部由环境变量提供。

### MCP 工具契约

工具名使用动词_名词形式，参数与返回均为 JSON 对象；所有错误通过工具的 `isError` 标记与结构化 `error` 字段返回，不抛传输层异常。

```text
submit_owner_command
  in:  task_node_id: str, command: str, idempotency_key: str, execution_id: str | null
  out: command_id, execution_id, task_node_id, session_id,
       command_status, execution_status, duplicate: bool
  规则: idempotency_key 唯一；相同键返回既有执行且 duplicate=true；
       带 execution_id 时视为续接该次执行（用于 waiting 后的回答）。

query_execution
  in:  execution_id: str
  out: execution_id, task_node_id, session_id, execution_status,
       result_summary: str | null, error_summary: str | null,
       pending_question: str | null
  规则: 不存在返回 isError 与 error=not_found；
       execution_status=waiting 时 pending_question 必填。

cancel_execution
  in:  execution_id: str
  out: execution_id, execution_status, accepted: bool
  规则: 已完成执行返回 accepted=false 与 error=not_cancellable。

list_pending
  in:  task_node_id: str | null
  out: executions: [{execution_id, task_node_id, execution_status, created_at}]
  规则: 只返回非终结状态（created、running、waiting）。

health
  in:  (无)
  out: status: "ready" | "unavailable", storage: bool
```

## Domain objects and state
- TaskSession：每个 task_node_id 一个稳定 session_id；状态 active、waiting、cancelled、failed、completed。
- OwnerCommand：幂等键唯一；状态 accepted、running、succeeded、failed、cancelled。
- ExecutionRecord：每次实际 Worker 尝试一条不可变记录；状态 created、running、waiting、succeeded、failed、cancelled。
- AuditEvent：追加记录命令接收、状态迁移、Worker 创建/退出、运行时结果、取消和错误摘要。

## Runtime and persistence
Gateway 核心只依赖 Runtime Adapter、Execution Store 和 Worker Scheduler。首版适配器分别为 fast-agent Runtime Adapter、SQLite Store 和本地进程 Scheduler。Gateway 在一个 SQLite 事务中创建 OwnerCommand、ExecutionRecord 初始记录和命令审计事件，然后调度 Worker。重复幂等键返回既有命令及其结果，不创建新的执行。

Runtime Adapter 至少支持 run、resume 和 cancel；同一 task_node_id 不能同时有两个 Worker。Worker 以固定 session_id 恢复 fast-agent Harness，会话 home 必须持久化。默认关闭自动 compaction。运行时异常、超时、非零退出或会话无法恢复时，ExecutionRecord 失败并保存错误摘要；Gateway 重启不自动重做已失败执行。

## Authentication and configuration
首版只支持本地开发令牌配置；真实令牌通过环境变量或本机安全配置注入，不能写入仓库。首版不实现多租户权限、跨网络 MCP、Redpanda、EventBus 或领域 MCP。

## Testing decisions
测试通过 MCP 工具的公共 seam 验证外部行为，不检查私有实现。必须覆盖：健康检查、首次命令提交、幂等重复提交、执行状态查询、Worker 成功、运行时失败、取消、同一 task_node_id 串行化、Gateway 重启后的会话恢复，以及使用 passthrough fast-agent 的最小运行时集成测试。真实模型凭据不进入测试。

## Out of scope
Research Mapping MCP、依赖图、Agent Kit/Skills/Hooks、ZIP 交付、跨服务器部署、Redpanda 上游交接、A2A 传输、真实模型提供商接入和生产级自动恢复。

## Acceptance Criteria

- [ ] MCP 工具接口、对象状态和 SQLite 持久化规则明确且可实现。
- [ ] 一次 Owner Command 能产生可查询的 ExecutionRecord 和 AuditEvent。
- [ ] 相同幂等键不会创建第二个执行。
- [ ] Worker 能通过 fast-agent Runtime Adapter 完成一次 loop 并释放。
- [ ] 固定 session_id 能在新的 Worker 中恢复。
- [ ] 失败、取消、串行化和 Gateway 重启读取行为有自动化验证。
- [ ] 规格未引入 MCP 领域逻辑、Agent Kit 或 ZIP 交付。

## Notes

**2026-10-19T08:53:34Z**

关联 Gitee Pull Request #9：https://gitee.com/qi-yueran/ai4science/pulls/9（目标 develop）。PR 包含 Gateway MVP 基础闭环、技术栈约束与实现路线图；后续实现票仍按依赖图推进。

**2026-10-19T20:12:00Z**

规格修订（2026-10-19）：Owner 通道由 HTTP 自定义端点改为 MCP（Streamable HTTP）。原因：主流 harness（Codex CLI、Cursor、Claude Code）对外扩展面只有 MCP，没有内置 A2A 客户端，Owner 无法直接作为 A2A 客户端接入。

- Public seams 改为 5 个 MCP 工具：`submit_owner_command`、`query_execution`、`cancel_execution`、`list_pending`、`health`。
- 保留 HTTP 回环端点，但只承担健康检查、本地调试和测试 seam，不再是 Owner 主通道。
- 不使用 stdio 传输：Codex 会自行 spawn 进程并随会话退出，破坏 Gateway 常驻、SQLite 单写者和跨会话串行调度。
- Out of scope 把“完整 A2A Human Input”改为“A2A 传输”；`waiting` 状态与待回答问题改由 `query_execution` 返回，Owner 用同一 `execution_id` 续接。

**2026-10-19T20:25:00Z**

补充 MCP 工具契约（2026-10-19）：在 Public seams 下增加逐工具的输入输出与错误规则，作为实现票和测试票的共同依据。要点：

- 所有工具返回 JSON 对象，错误经 `isError` 与结构化 `error` 字段表达，不抛传输层异常。
- `submit_owner_command` 的 `execution_id` 可空；非空表示续接该次执行，用于 `waiting` 后的回答。
- `query_execution` 在 `execution_status=waiting` 时必须返回 `pending_question`。
- `cancel_execution` 对已完成执行返回 `accepted=false` 与 `error=not_cancellable`。
- `list_pending` 只返回非终结状态。
- `health` 返回 `status` 与 `storage` 两个字段。
