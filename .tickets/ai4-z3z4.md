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
tags: [spec, task-agent, fast-agent, ready-for-agent]
---
# 最小 Task Agent 项目组实现规格

将“Gateway 与最小 fast-agent 执行闭环规格地图”的已决边界收敛为一个可交付的 Task Agent 实现规格。该规格覆盖同一部署单元中的 MCP Gateway、上游 ingest、共享持久化和短生命周期 Worker；它是后续实现 tickets 的唯一上游输入。

## Problem Statement

Task Owner 需要通过其 Codex 等 MCP 客户端提交受控命令、观察执行过程、回答暂停问题、取消执行并审核执行结果。平台还需要为未来正式上游交接保留独立入口，而不会让上游消费者绕过同一 TaskNode 的串行化和审计边界。

当前已有一个仅含 HTTP/SQLite 基础行为的 Gateway MVP，以及 ingest 和 Worker 的可安装骨架；它们尚未形成可认证的 MCP Owner 通道、统一持久化状态机、原子 Worker 租约或 fast-agent 执行闭环。

## Solution

实现一个最小 Task Agent 项目组。Gateway 组件组是唯一的 Worker 启动与串行化边界：MCP 入口接收 Owner 请求，ingest 入口为未来正式上游交接预留；两个入口均经共享 SQLite 持久化层保存事实、领取同一 TaskNode 的 Worker Lease（Worker 租约），再启动短生命周期 Worker。Worker 经 fast-agent Runtime Adapter 完成一次 loop 后退出。

Owner 主通道为认证后的 MCP Streamable HTTP。Gateway 使用本地开发 Bearer 令牌及配置的 Caller（调用者）标识；OwnerCommand 只记录命令接收事实，ExecutionRecord 是唯一的 Gateway 工作流状态机。回环 HTTP 仅提供最小健康探针，不构成第二条 Owner API。领域 Buffer 不在本阶段设计或自动创建。

## User Stories

1. 作为 Task Owner，我希望通过 MCP 提交带幂等键的任务命令，以便网络重试不会启动第二次执行。
2. 作为 Task Owner，我希望提交后立即获得稳定的命令和执行标识，以便异步跟踪执行而不等待 Worker 完成。
3. 作为 Task Owner，我希望查询某个执行的状态、会话、结果摘要、错误摘要和待回答问题，以便恢复工作上下文。
4. 作为 Task Owner，我希望列出待跟进执行，以便发现等待回答、等待审核或仍在排队的任务。
5. 作为 Task Owner，我希望取消一个未终结执行，以便停止不再需要的工作；重复取消或已终结执行可安全得到未接受取消的结果。
6. 作为 Task Node Owner，我希望审核可审核的执行结果并接纳、要求返修、驳回或请求人工接管，以便让执行结果具有可审计的处置结论。
7. 作为 Task Owner，我希望在 Worker 提问后提交回答，以便以同一稳定会话启动新的恢复执行，而不依赖旧进程仍存活。
8. 作为本地开发者，我希望未携带正确令牌的请求在进入 MCP 工具前被拒绝，以便不会污染任务事实和审计链。
9. 作为本地开发者，我希望已认证请求以配置的 Caller 记录，以便审计能说明请求来源，但不伪装为已具备 TaskNode 授权。
10. 作为 Gateway 维护者，我希望 MCP 与 ingest 可重复安全初始化同一 SQLite schema，以便进程重启或重复部署不会破坏既有执行记录。
11. 作为 Gateway 维护者，我希望同一 TaskNode 在任意时刻只有一个入口能获得有效 Worker Lease，以便不会并发启动两个 Worker。
12. 作为 Gateway 维护者，我希望不同 TaskNode 在资源允许时可以分别执行，以便不把全局吞吐量限制为单 Worker。
13. 作为上游集成者，我希望未来的正式上游交接能进入 ingest，并和 Owner 命令共享调度和审计规则，以便不会绕过 Gateway 边界。
14. 作为调度器，我希望必要上游尚未正式就绪时保留 Owner 命令为 blocked，以便命令事实不会丢失或被过早执行。
15. 作为调度器，我希望上游就绪后的首轮执行优先于尚未完成首轮的普通 Owner 命令，以便先建立任务所需的上游基础。
16. 作为 Worker，我希望获得稳定 session_id、持久 home、connection scope 和 session history，以便新的短生命周期进程能够恢复会话。
17. 作为 Worker，我希望每次完成、暂停或失败后退出，以便 Gateway 保持为常驻控制面而非长期占用执行进程。
18. 作为维护者，我希望运行时异常、超时、非零退出和会话恢复失败都被记录为 failed，以便故障可查询而不自动重做。
19. 作为维护者，我希望健康信息聚合 SQLite、MCP、ingest 队列和 Worker runtime 的实际可用性，以便诊断配置缺失、降级和不可用状态。
20. 作为本地探针，我希望无需 MCP 令牌取得最小健康状态和 API 版本，以便检测服务存活而不暴露内部组件详情。
21. 作为领域治理使用者，我希望执行结果接纳不自动写入 Research Mapping、LLM-Wiki 或 Buffer，以便领域提交继续经过显式 MCP 和治理流程。
22. 作为实现者，我希望对外测试只经 MCP 工具和最小 HTTP 探针验证，以便实现可在不破坏客户端行为的前提下重构。

## Implementation Decisions

### 项目组与进程边界

- Task Agent 是一个项目组，包含 `gateway/mcp`、`gateway/ingest` 和 `worker` 三个独立 Python 子项目，共用项目组级 uv workspace、锁文件和跨角色环境配置。
- `gateway/mcp` 是常驻 MCP Server，处理 Owner MCP 请求；`gateway/ingest` 是常驻上游交接消费者；`worker` 是一次 loop 一个进程的短生命周期角色。
- Gateway 组件组，即 `mcp` 与 `ingest` 及其共享持久化契约，是唯一可启动 Worker 并裁决同 TaskNode 串行化的边界。组件组外客户端和消费者不得启动 Worker。
- 共享 SQLite 持久化包提供 schema、幂等 bootstrap、受约束表访问、状态迁移校验、Worker Lease、审计与健康读写；不包含 MCP、消息队列或 Worker 业务。
- 首版仅需要幂等 bootstrap；已有数据库的结构升级另行设计 migration。

### Owner MCP v1 协议

- Owner 通道采用 MCP Streamable HTTP；不采用 stdio，因为客户端进程生命周期不能承载常驻 Gateway 的持久调度职责；不采用 A2A，因为它不是 Owner harness 的既定扩展面。
- MCP 初始化承担 MCP 协议版本协商；认证后的 `health` 返回 `gateway_api_version: "v1"`。v1 只能兼容性新增可选字段或工具；删除字段、收紧字段或改变既有语义时升级主版本。
- 所有成功工具结果仅在 MCP `content` 中返回一个 JSON 文本对象；首版不声明 `outputSchema`，不返回 `structuredContent`。
- 无效 JSON-RPC、未知工具、缺失必填参数和类型不符由 MCP/JSON-RPC 协议错误表达。已通过参数校验并进入工具后的业务失败以 `isError: true` 返回 JSON 文本 `{ "error": { "code", "message" } }`。
- 最小业务错误码为 `not_found`、`invalid_state`、`unavailable` 和 `internal`。错误不得包含令牌、异常、堆栈、文件路径或原始命令。
- `submit_owner_command(task_node_id, command, idempotency_key, execution_id?)` 在单个 SQLite 事务中创建命令接收事实、初始 ExecutionRecord 和审计事件；返回 command_id、execution_id、task_node_id、session_id、execution_status 与 duplicate。`execution_id` 只用于回答 waiting 后的问题，并创建 `resume_of` 关联的新记录。
- `query_execution(execution_id)` 返回执行、任务、会话、稳定状态、结果/错误摘要、待答问题、trigger 和 trigger_ref；不存在时返回 `not_found`。
- `cancel_execution(execution_id)` 对存在的执行总返回 execution_id、execution_status 和 accepted。accepted 仅表示本次取消请求被 Gateway 接受；已终结、人工接管或已取消时为 false。不存在时返回 `not_found`。
- `list_pending(task_node_id?)` 一次返回 blocked、queued、running、waiting 与 awaiting_acceptance 的全部记录，按 created_at、execution_id 升序；首版不分页。
- `review_execution(execution_id, decision, reason, idempotency_key)` 支持 `accept`、`request_revision`、`reject` 与 `request_human_takeover`；返回处置后的执行状态、可选后继执行标识和 duplicate。
- `health()` 返回聚合状态和 MCP、消息队列、Worker runtime、存储与调度器分项状态。
- `submit_owner_command` 与 `review_execution` 的幂等键仅在各自工具内全局唯一；重复键始终返回首次持久化结果并标记 duplicate=true，不比较后续参数。调用者为每个逻辑操作提供新键。

### 身份、配置与健康

- 每个 MCP HTTP 请求均需 `Authorization: Bearer <token>`；令牌和 `caller_id` 都由环境变量提供。校验成功后，将 Caller 写入 OwnerCommand 与 AuditEvent。
- 缺失或无效令牌返回 HTTP 401，不创建 OwnerCommand、ExecutionRecord 或 AuditEvent。首版不实现 OAuth、scope、多人身份、TaskNode Owner 授权绑定或跨网络部署。
- 所有部署路径、监听地址、端口、令牌、数据库位置、Worker 持久目录和服务地址均由环境变量配置；仓库只保留变量示例，不提交真实凭据。
- 回环 HTTP 健康探针不要求令牌，只返回 `status` 和 `gateway_api_version`；认证 MCP `health` 返回完整分项健康。二者复用一套健康计算。
- SQLite 可读写且 schema 兼容是核心条件；核心存储故障为 unavailable。已配置的必需组件故障为 degraded，未配置组件为 not_configured，所有已配置组件满足条件时为 ready。

### 持久化、状态和调度

- TaskSession 为每个 task_node_id 持有稳定 session_id；它是会话投影，不替代 ExecutionRecord 的审计事实。
- OwnerCommand 仅记录已接收的原始意图、Caller、幂等键、时间和关联结果，是不可变审计留痕，不维护独立生命周期状态机。
- ExecutionRecord 是唯一的 Gateway 工作流状态机和一次可追踪执行尝试。它保存触发来源、会话、输入摘要及哈希、起止时间、结果/错误摘要与审计关联。
- ExecutionRecord 的稳定状态为：

```text
blocked → queued → running
                    ├→ waiting
                    ├→ awaiting_acceptance → accepted | needs_revision | rejected | human_takeover
                    ├→ failed
                    └→ cancelled
```

- `blocked` 表示必要上游尚未正式发布；满足条件后转为 `queued`。`waiting` 终结本轮记录；Owner 回答创建以 `resume_of` 关联的新记录。`request_revision` 将原记录处置为 `needs_revision` 并创建 `revision_of` 新记录；系统重试创建 `retry_of` 新记录。`accepted` 只表示 TaskNode Owner 已接纳执行结果，不代表 Project Owner 正式发布。
- 审计事件追加记录命令接收、排队、状态转换、租约取得/释放、Worker 生命周期、运行时事实、审核决定、取消和无敏感信息的错误摘要。
- 同一 task_node_id 只允许一条有效 Worker Lease。两个入口通过 SQLite 原子条件领取启动权；未领取不得启动第二个 Worker。可领取执行按 created_at、execution_id 稳定排序。
- Owner 命令在首次上游执行前可为 blocked。上游就绪的首轮执行优先于尚未完成首轮的普通 Owner 命令；取消不受此优先规则阻止。
- 租约失效不覆盖旧记录；恢复必须创建关联旧记录的新记录。续租周期、超时阈值及具体接管算法不在本规格实现。

### Runtime Adapter 与 Worker

- Gateway 核心依赖 Execution Store、Worker Scheduler 和 Runtime Adapter；首版具体实现分别为共享 SQLite、本地进程调度和 fast-agent Runtime Adapter。
- Runtime Adapter 至少提供 run、resume 与 cancel。Worker 使用固定 session_id、专属持久 home、connection scope 和 session history，默认关闭自动 compaction。
- Worker 成功生成可审核结果时将执行转为 awaiting_acceptance；运行时异常、超时、非零退出或无法恢复会话时转为 failed。Gateway 重启可读取未完成记录，但不自动重做 failed 记录。
- `review_execution(decision="accept")` 仅写 SQLite 审核事实和 AuditEvent；不会自动创建领域草稿、领域 Buffer 或 outbox。
- Mapping 初始化查询契约仍依赖 Research Mapping 工作完成；当前 Gateway 不假定该接口，不自动放行 blocked 记录，也不实现 ingest 消费。

## Testing Decisions

- 以认证后的 MCP 工具调用作为最高且主要的行为测试接缝；测试不检查私有类、表访问顺序、子进程实现细节或日志格式。
- 回环 HTTP 探针只测试其最小健康结果以及与 MCP `health` 共用健康计算的可观察结果。
- 使用临时 SQLite 数据库、临时持久目录、回环地址和系统分配端口 `0`；不得依赖固定部署端口、真实令牌、真实模型凭据或外部队列。
- 在 MCP 入口验证：认证拒绝、命令首次提交、工具内重复幂等提交、命令审计留痕、blocked 查询、状态查询、取消幂等语义、待处理排序、审核决定与稳定错误码。
- 在共享持久化与调度边界验证：重复 bootstrap、非法状态迁移拒绝、Gateway 重启后读取、同 TaskNode 原子租约和串行化、跨 TaskNode 可并发、上游优先和取消例外。
- 在 Worker/Runtime Adapter 边界验证：成功进入 awaiting_acceptance、运行时失败、waiting 后产生 resume_of、返修后产生 revision_of、固定会话恢复、Worker 退出和租约释放。
- 使用 passthrough fast-agent 运行最小集成测试；真实模型提供商不进入测试。
- 项目组级验证至少包含 uv 环境同步、三个子项目可安装、源码编译和 MCP 行为测试；ingest 在未选定队列前只验证其可启动的受控未实现/未配置行为。

## Out of Scope

- Research Mapping 或 LLM-Wiki 的领域 MCP、领域 Buffer 及其状态机、Mapping 写入和领域 outbox。
- 多人身份、TaskNode Owner 授权绑定、OAuth 授权服务器、scope、跨网络或生产级认证部署。
- Redpanda 或其他消息队列产品选型和实际 ingest 消费实现。
- Agent Kit manifest、Skills/Hooks 模板、多套件定制、ZIP 交付、跨服务器部署。
- A2A 传输、EventBus、真实模型提供商接入、原件二进制传输、生产级自动恢复和租约接管算法。
- 既有 SQLite 数据库 schema migration 方案。

## Further Notes

- 本规格取代此前只覆盖单一 Gateway 的实现视角，统一覆盖 Task Agent 项目组三角色及其共享边界。
- 已决依据包括“Gateway MVP 状态模型与端口边界”、“Owner 通道与上游交接队列物理隔离”、“执行与接纳状态机融合及 Owner 审核工具边界”、“Task Agent 项目组三角色部署与双入口调度边界”和“Gateway MCP 对外协议版本、鉴权与错误契约”。
- 现有 HTTP/SQLite MVP 是迁移起点，不是最终 Owner 协议；实现须以本规格的 MCP v1、单一 ExecutionRecord 状态机和共享 SQLite 约束为准。

## Acceptance Criteria

- [ ] 三角色 Task Agent 项目组、共享 SQLite 持久化边界、单一 Worker 启动权和对外 MCP v1 契约均已实现。
- [ ] 认证后的 Owner MCP 调用可创建、查询、取消、列出、审核和恢复执行；未认证请求不会创建领域或执行审计事实。
- [ ] OwnerCommand 仅作为命令接收留痕，ExecutionRecord 是唯一工作流状态机，且所有稳定状态迁移均经审计。
- [ ] 同一 TaskNode 不会并发启动 Worker；Worker 使用固定会话恢复并在一次 loop 后退出。
- [ ] 接纳执行结果不会创建任何领域 Buffer、草稿或 outbox。
- [ ] 健康状态、未配置组件、降级与不可用状态均可从规定的 MCP 或最小 HTTP 接缝观察。
- [ ] 全部测试决策所列行为均有自动化验证，且不依赖真实模型凭据、固定端口或未选定队列。

## Notes

**2026-10-20T07:32:36Z**

2026-10-20：按“整体实现”重新发布为《最小 Task Agent 项目组实现规格》，覆盖 gateway/mcp、gateway/ingest、worker、共享 SQLite、租约、最小 MCP v1、Caller、单一 ExecutionRecord 状态机、健康和测试边界；标记 ready-for-agent。已验证：fer dep cycle 无依赖环；git diff --check 通过。
