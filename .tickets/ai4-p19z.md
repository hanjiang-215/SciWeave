---
id: ai4-p19z
status: open
deps: []
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# MCP v1 命令闭环与共享执行持久化

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

Task Owner 可通过带本地 Bearer 令牌的 MCP Streamable HTTP 提交命令、查询执行并读取健康状态。请求持久化 Caller、OwnerCommand 留痕、TaskSession、初始 ExecutionRecord 和 AuditEvent；回环 HTTP 仅暴露最小健康探针。

## Acceptance Criteria

## Acceptance Criteria

- [ ] `submit_owner_command`、`query_execution` 与 `health` 经认证 MCP 可端到端调用。
- [ ] 共享 SQLite 可重复 bootstrap，持久化 Caller、命令留痕、会话、初始 `blocked` 或 `queued` 执行和审计事件。
- [ ] 工具内幂等键重复调用返回首个持久化结果及 `duplicate=true`，不会创建第二条命令或执行。
- [ ] 缺失或无效令牌返回 HTTP 401 且不创建任务事实；协议错误与工具业务错误保持规定边界。
- [ ] 无令牌回环探针仅返回状态和 API 版本，认证 MCP `health` 报告规定的分项健康。
- [ ] 自动化测试仅经 MCP 和最小 HTTP 健康接缝验证。
