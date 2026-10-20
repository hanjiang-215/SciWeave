---
id: ai4-wdvf
status: closed
deps: [ai4-o806, ai4-yvh2]
links: []
created: 2026-10-19T07:24:35Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [test, gateway, fast-agent]
---
# Gateway MVP 与最小 fast-agent 集成验收

通过 Gateway 的 MCP 工具公共 seam 验证完整最小闭环：命令提交、幂等、短生命周期 Worker、fast-agent loop、结果查询、失败、取消、TaskNode 串行化、Gateway 重启读取和固定会话恢复。该票不扩展到真实模型、领域 MCP、Redpanda、A2A 或 ZIP。

## Acceptance Criteria

- [ ] 集成测试覆盖健康检查、合法命令提交、执行状态查询和最终成功结果。
- [ ] 集成测试覆盖重复幂等提交、运行时失败、取消、同一 task_node_id 串行化和 Worker 释放。
- [ ] 集成测试覆盖 Gateway 重启后的状态读取和新 Worker 使用固定 session_id 恢复。
- [ ] 测试使用 passthrough fast-agent，不需要或保存真实模型凭据。
- [ ] 测试从 MCP 工具的公共 seam 观察行为，不依赖私有函数或内部实现细节。
- [ ] 验证命令、结果、提交和遗留风险回写本票。

> 修订（2026-10-19）：Owner 通道改为 MCP（Streamable HTTP），原“HTTP 公共 seam”改为“MCP 工具公共 seam”，覆盖 `submit_owner_command`、`query_execution`、`cancel_execution`、`list_pending`、`health`。回环 HTTP 端点只用于健康检查和本地调试。背景见 [Owner 通道与上游交接队列物理隔离](ai4-353s.md)。

## Notes

**2026-10-20T07:47:45Z**

2026-10-20：废弃，不再实施。该票的验收前提是旧 HTTP MVP 票链，已由《最小 Task Agent 项目组端到端验收》（ai4-iyyn）替代；新票覆盖 MCP v1、控制工具、共享租约和固定会话恢复。保留为历史实现计划。
