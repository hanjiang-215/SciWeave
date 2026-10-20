---
id: ai4-b8vm
status: closed
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

> 入口修订（2026-10-19）：Owner 通道改为 MCP（Streamable HTTP）。本票的调度器与 Runtime Adapter 不依赖入口协议，实现时按 MCP 工具层传入的 Owner Command 处理即可。见 [Owner 通道与上游交接队列物理隔离](ai4-353s.md)。

## Acceptance Criteria

- [ ] Owner Command 可以触发一个短生命周期本地 Worker。
- [ ] Gateway 核心通过 Runtime Adapter 的 run、resume 和 cancel 能力调用运行时，不直接依赖运行时内部实现。
- [ ] 同一 task_node_id 同时只有一个 Worker 执行，后续命令排队或按约定返回状态。
- [ ] Worker 创建、启动、成功退出、失败退出和释放均写入 ExecutionRecord/AuditEvent。
- [ ] 运行时异常、超时、非零退出和取消请求会形成可查询的失败或取消状态。
- [ ] 已完成执行不可被取消，取消请求不会伪造成功结果。

## Notes

**2026-10-20T07:47:45Z**

2026-10-20：废弃，不再实施。该票未覆盖共享 SQLite Worker Lease、三角色项目组和当前稳定状态机，已由《带 Worker Lease 的本地调度与测试运行时》（ai4-m96w）整体替代。保留为历史实现计划。
