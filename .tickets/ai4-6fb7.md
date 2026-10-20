---
id: ai4-6fb7
status: closed
deps: []
links: []
created: 2026-10-20T03:43:14Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling, task-agent, gateway]
---
# Task Agent 项目组三角色部署与双入口调度边界

收敛 Task Agent 项目组的目录、角色、健康、共享 SQLite、双入口 Worker 启动与上游优先规则；不设计领域 Buffer 本体、消息队列产品或具体恢复算法。

## Design

已确认：`task-agent` 是总项目组；`gateway` 是组件组，含 `mcp` 与 `ingest` 两个独立 Python 子项目；`worker` 是独立短生命周期子项目。`mcp` 接收 Codex 的 MCP 调用，`ingest` 消费正式上游交接；二者不共享代码，但可共享 SQLite。Task Agent Gateway 组件组是唯一 Worker 启动与串行化边界：`mcp` 与 `ingest` 都可在共享 SQLite 中为同一 `task_node_id` 原子取得执行租约后启动同一个 `worker` 子项目，未取得租约不得启动第二个 Worker；组件组外的队列消费者或客户端不得启动 Worker。上游交接驱动的首轮优先，Owner 命令可先持久化为 `blocked`。统一 health 接口分项报告 MCP 和消息队列状态；正式交付内容写未来领域 Buffer，本票不设计 Buffer。

## Acceptance Criteria

明确项目组、组件组和子项目目录及独立 pyproject.toml 边界；明确统一 health 接口的 MCP/队列分项语义；明确 SQLite 表归属、双入口原子租约、Worker 启动权与上游优先规则；明确 Owner 命令在上游阶段的 blocked/放行语义；明确崩溃恢复所需决策与领域 Buffer 的排除边界。

## Notes

**2026-10-20T06:40:31Z**

## Resolution

Task Agent 采用三角色项目组：`gateway/mcp` 处理 Owner MCP 调用，`gateway/ingest` 处理正式上游交接，`worker` 是短生命周期执行进程；Gateway 组件组是唯一 Worker 启动与串行化边界。

`mcp` 与 `ingest` 通过项目组内共享 SQLite 持久化包协作。该包提供 schema、幂等 bootstrap、受约束的表访问接口、状态迁移校验、执行租约、审计与健康读写；不包含 MCP、消息队列或 Worker 业务逻辑。首次或重复启动均可安全 bootstrap；未来需要升级既有数据库结构时再单列 migration 设计。

同一 `task_node_id` 同时只有一个有效 Worker 租约。领取必须是 SQLite 原子条件写入；未取得租约不得启动 Worker。可领取的执行按 `ExecutionRecord.created_at`、`execution_id` 的稳定顺序处理；上游就绪后的首次执行优先于尚未完成首轮的普通 Owner 命令。租约失效不覆盖旧记录，后续恢复以新记录关联旧记录；续租、超时阈值和具体接管策略留给后续调度实现细化。

Owner 命令在首次上游执行前可持久化为 `blocked`；取消不受该优先规则阻止。Task Agent 初始化所需的 Mapping 只读查询仍受 Research Mapping 开发阻塞，已由“Task Agent 初始化所需的 Mapping 查询契约”单独承载；当前 Gateway 不假定该接口，也不实现自动放行或 ingest 消费。

健康计算以实际可用性为准：SQLite 可读写、schema 兼容是核心条件；MCP 以 listener、鉴权和可调用 `health` 验证；ingest 以队列连接和 SQLite 心跳验证；Worker runtime 以可启动命令、已声明依赖和持久目录可访问验证，不要求 Worker 常驻。未配置组件报告 `not_configured`，核心存储不可用时总状态为 `unavailable`，已配置必需组件故障时为 `degraded`，全部已配置组件满足条件时为 `ready`。回环 HTTP 探针与 MCP `health` 复用同一健康计算。

领域 Buffer、消息队列产品选型、Mapping 写入和具体崩溃恢复算法不属于本票。
