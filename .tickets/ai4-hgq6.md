---
id: ai4-hgq6
status: open
deps: [ai4-g5fx]
links: [ai4-10ja, ai4-te1v, ai4-9mf8]
created: 2026-10-26T08:21:32Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-10ja
tags: [implementation, centre-control, handoff, ready-for-agent]
---
# 根任务不自动派发并实现显式分派

## What to build

没有上游依赖的根 TaskNode 只能由 PO 显式分派，不能因为「没有任何前置条件不满足」就自动开工。同时补上 `dispatch_root_task` 这条路径——它在 `src/` 和 `tests/` 里都还不存在。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] 无入边根节点在任意正式版本发布后不自动派发，不产生 `task_handoff_ready`。
- [ ] 根节点在自动重算路径下留下 `waiting` 事实，而不是被跳过到无从观察。
- [ ] 实现 `dispatch_root_task`，可显式派发指定根节点，产出与自动派发形状相同的 `task_handoff_ready`。
- [ ] `dispatch_root_task` 幂等：同一根节点重复调用只产生 1 条 dispatch 与 1 条消息。
- [ ] 对有入边的非根节点调用 `dispatch_root_task` 时被拒绝，不改动任何状态。
- [ ] 新增测试：根节点不自动派发、显式派发成功、重复调用幂等、对非根节点被拒；前两项在修复前失败。
- [ ] 既有 9 项测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 「无入边」不是条件平凡满足，而是不满足可自动派发条件。当前用 `all(...)` 在空集合上得真，把结构缺失当成了条件成立。
- 接口契约由 `ai4-9mf8`（已关闭）定义，本票只实现协调器侧。PO 经高权限 MCP 调用，不直接操作队列。
- 显式分派产出的消息与自动派发同类型，不引入 `root_task_dispatched` 之类的额外事件——`ai4-te1v` 已明确不需要。
