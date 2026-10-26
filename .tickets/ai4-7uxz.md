---
id: ai4-7uxz
status: open
deps: [ai4-g5fx]
links: [ai4-10ja, ai4-te1v]
created: 2026-10-26T08:21:32Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-10ja
tags: [implementation, centre-control, handoff, ready-for-agent]
---
# 按声明顺序选择可用执行者

## What to build

`executor_refs` 配了多个执行者时，按声明顺序取第一个可用的那个。现在写死取第一个，第一个离线就判定「无可用执行者」并转人工，即使第二个在线。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] `executor_refs=(a1, a2)` 且仅 `a2` 可用时，派发给 `a2`，不产生人工通知。
- [ ] `executor_refs` 全部不可用时，不发布 `task_handoff_ready`，保留 `waiting` 并产生 `human_notification_intent`。
- [ ] `executor_refs` 为空时同样转人工，受影响的 `notification_kind` 由 `ai4-xkbd` 决定。
- [ ] `target_agent_id` 记实际选中的执行者，不是列表第一个。
- [ ] `executor_ref_snapshot` 记完整快照（所有 `executor_refs`），供事后分辨「当时没有别的执行者」与「当时有但选错了」。
- [ ] 两处选择逻辑（快照全量重算与下游重算）共用同一个选择函数，不各写一份。
- [ ] 新增测试：多执行者择一、全部不可用、空列表；第一项在修复前失败。
- [ ] 既有 9 项测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 顺序即偏好。按声明顺序选，不随机、不并发探测、不按负载均衡——配置者写下顺序就是在表达优先级。
- 可用性判断只问「能不能接活」，不构成授权。执行资格仍由正式 Map 的 `executor_refs` 决定，Registry 事实不能扩权。
- 注意 `_evaluate_snapshot` 与 `_recompute_downstream` 两处都有这段逻辑，抽一处共用，否则下次改选择规则会漏掉一边。
