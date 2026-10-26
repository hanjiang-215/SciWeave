---
id: ai4-g5fx
status: open
deps: []
links: [ai4-10ja, ai4-2raq, ai4-edrp]
created: 2026-10-26T08:21:32Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-10ja
tags: [implementation, centre-control, handoff, prefactor, ready-for-agent]
---
# 扩展协调器端口与快照字段

## What to build

在不改变任何现有行为的前提下，把后续五个缺陷修复需要的接口先立起来，并且现有 9 项测试全部照绿。这样五个修复可以各自独立开工，不必挤在同一批改动里改构造签名。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] `FormalSnapshot` 新增 `latest_published_by` 字段，可为 `None`；注释链到 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)，写明它回答「最近一次批准者是谁」而非「谁被任命为负责人」。
- [ ] 新增 `PrincipalDirectoryPort`，能查询某个 `principal_id` 是否存在且状态为 `active`；Registry 不可用时能表达「无法判断」，而不是返回 False。
- [ ] `CoordinatorService` 构造函数接受该端口，缺省为不校验的实现，现有调用点无需修改。
- [ ] `HandoffReadyMessage` 补齐 `upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot` 三个字段，与 `ai4-te1v` 的载荷要求一致。
- [ ] `dependency_edge_version_refs` 为元组/数组，单元素时仍是数组。
- [ ] 现有 9 项测试不改断言、全部通过。
- [ ] 新增测试：`FormalSnapshot` 带 `latest_published_by` 时可构造；`PrincipalDirectoryPort` 的三种结果（存在且 active、不存在、无法判断）各有覆盖。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- **只加不接线。** 本票不改变任何派发、通知或状态迁移行为；新字段与新端口加进来但没人读，是预期状态。
- 为什么不并入某一个修复票：`PrincipalDirectoryPort` 会改 `CoordinatorService` 的构造签名，而所有测试都经由 `make_service` 组装。先做一次无行为变更的扩展，后续五张票才能并行且互不冲突。
- `latest_published_by` 的真实数据由 `ai4-2raq` 与 `ai4-edrp` 提供；本票只让类型上能承载，测试直接构造。
- `executor_ref_snapshot` 与 `upstream_source_refs` 的语义见 `ai4-te1v`「统一消息信封」，不要在此重新定义。
