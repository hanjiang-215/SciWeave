---
id: ai4-vqkn
status: closed
deps: [ai4-0nuq, ai4-yvh2]
links: []
created: 2026-10-19T07:24:35Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, gateway]
---
# Owner Command 幂等与 Execution 状态持久化

在 Gateway 基础命令闭环上补齐可靠状态语义：同一个 idempotency_key 只对应一个 OwnerCommand 和一个执行，不因重复请求产生第二次执行；执行状态和审计事件可以在 Gateway 重启后读取。

## Acceptance Criteria

- [ ] idempotency_key 具有持久化唯一约束。
- [ ] 重复提交相同 task_node_id、命令内容和幂等键返回原 command_id、execution_id 和当前状态。
- [ ] 重复提交不会创建第二个 ExecutionRecord 或重复的命令接收事实。
- [ ] 支持 accepted、running、succeeded、failed、cancelled 状态迁移，并拒绝非法迁移。
- [ ] 状态迁移追加 AuditEvent，错误摘要不包含凭据。
- [ ] 关闭并重新创建 Gateway 后可以读取既有 TaskSession、ExecutionRecord 和 AuditEvent，不自动重做已失败执行。

> 入口修订（2026-10-19）：Owner 通道改为 MCP（Streamable HTTP）。MCP 客户端重试可能重复发送同一次工具调用，因此幂等键需要在 MCP 工具层显式传入，不能依赖传输层去重。字段名与回环 HTTP 端点保持一致，仍为 `idempotency_key`。背景见 [Owner 通道与上游交接队列物理隔离](ai4-353s.md)。

## Notes

**2026-10-20T07:47:45Z**

2026-10-20：废弃，不再实施。该票基于旧 HTTP seam、旧 OwnerCommand/ExecutionRecord 状态术语和单一 Gateway 假设，已由《MCP v1 命令闭环与共享执行持久化》（ai4-p19z）整体替代。保留为历史实现计划。
