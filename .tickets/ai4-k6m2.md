---
id: ai4-k6m2
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, centre-agents]
---
# centre-agents 处置面：list_pending 语义与 cancel_execution 行为不符契约

list_pending 返回包含 completed/failed/cancelled 的全量记录，而 docs/data-flow/work-agent.md 定义的是需人介入的记录，needs_revision/human_takeover 反被排除。cancel_execution 只把状态改成 cancelled，Worker 结束时的终态 UPDATE 无 status=running 守卫，几秒后又被覆盖成 completed，且从不调用 runtime.cancel()。

## Acceptance Criteria

list_pending 返回 queued/running/waiting/needs_revision/human_takeover。|终态写入加 AND status = 'running' 守卫，取消先落 cancel_requested。|补 cancel 的端到端测试与 list_pending 集合断言。

