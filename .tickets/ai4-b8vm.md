---
id: ai4-b8vm
status: open
deps: [ai4-vqkn]
links: []
created: 2026-10-19T07:24:35Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, gateway, runtime]
---
# 本地 Worker Scheduler 与 Runtime Adapter

让已持久化的 Owner Command 进入短生命周期 Worker 执行流程：Gateway 通过 Runtime Adapter 调用一次运行时，按 task_node_id 串行化执行，记录 Worker 生命周期，并支持查询、失败和取消。首版使用测试 Runtime 验证调度器，不接入领域 MCP、Redpanda 或 A2A。

## Acceptance Criteria

- [ ] Owner Command 可以触发一个短生命周期本地 Worker。
- [ ] Gateway 核心通过 Runtime Adapter 的 run、resume 和 cancel 能力调用运行时，不直接依赖运行时内部实现。
- [ ] 同一 task_node_id 同时只有一个 Worker 执行，后续命令排队或按约定返回状态。
- [ ] Worker 创建、启动、成功退出、失败退出和释放均写入 ExecutionRecord/AuditEvent。
- [ ] 运行时异常、超时、非零退出和取消请求会形成可查询的失败或取消状态。
- [ ] 已完成执行不可被取消，取消请求不会伪造成功结果。
