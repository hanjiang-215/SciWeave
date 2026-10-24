---
id: ai4-zc85
status: open
deps: []
links: []
created: 2026-10-23T14:07:18Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-p5f3
tags: [wayfinder:grilling, centre-control, coordinator, handoff, message-queue]
---
# handoff coordinator 依赖重算与派发恢复规格

先于 coordinator 实现，明确正式 Mapping 事件输入、原子快照查询端口、PendingHandoff/HandoffDispatch 状态、任务交接与人工通知输出、无后继检测和启动恢复边界。Research Mapping MCP 访问传输仍受 ai4-2982 约束。

## Design

只形成服务规格，不写代码。需要决定协调服务输入输出事件、幂等键、状态迁移、快照版本检查、无后继与待推进区别、派发结果未知、重试/死信和补偿扫描。不得直连 Research Mapping SQLite/TerminusDB。

## Acceptance Criteria

- 明确 formal_revision_published/根任务触发输入和正式快照查询端口\n- 明确 PendingHandoff/HandoffDispatch 最小 schema、状态迁移和幂等键\n- 明确 task_handoff_ready、human_notification_intent、task_terminal_summary 输出条件\n- 明确无后继、条件未满足、Agent 不可用、查询失败和派发结果未知的区别\n- 明确启动恢复、补偿扫描、重试、死信和不修改正式 Map 边界\n- 形成可供 coordinator 实现票引用的接口与验证契约

