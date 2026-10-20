---
id: ai4-6fb7
status: open
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
