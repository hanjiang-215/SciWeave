---
id: ai4-9wji
status: open
deps: [ai4-g5fx, ai4-br61]
links: [ai4-10ja, ai4-7uxz, ai4-edrp, ai4-br61, ai4-te1v]
created: 2026-10-26T12:33:10Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-10ja
tags: [implementation, centre-control, handoff, ready-for-agent]
---
# 交接载荷补齐 upstream_source_refs 与 executor_ref_snapshot

## What to build

`task_handoff_ready` 现在发出去时，`upstream_source_refs` 与 `dependency_edge_version_refs` 两个字段永远是空元组。`ai4-g5fx` 把字段加进了 `HandoffReadyMessage`，但两处构造点仍只传原来六个参数，没有填值。端侧 Task Agent 收到消息后无法知道这次交接依据哪几个正式版本，只能自己再查一遍正式 Map——而这正是载荷本该回答的问题。

本票只做填值，不改派发、通知与状态迁移行为。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md) 与 [`2026-10-26-message-envelope-protocol-package-design.md`](../docs/superpowers/specs/2026-10-26-message-envelope-protocol-package-design.md)。

## Acceptance Criteria

- [ ] `_dispatch_ready` 构造的 `HandoffReadyMessage` 携带真实的 `upstream_source_refs` 与 `dependency_edge_version_refs`，不再是空元组。
- [ ] `_publish_dispatch`（启动恢复重发）构造的 `HandoffReadyMessage` 与首次派发填同一份数据，两处不各算一遍。
- [ ] `upstream_source_refs` 取自当前正式快照中该节点的全部入边来源，元素为 `(node_id, version_id)` 二元组，顺序与 `incoming_edges` 一致。
- [ ] `dependency_edge_version_refs` 取自同一批入边，元素为 `(edge_id, edge_version_id)` 二元组，第二位来自 `ai4-br61` 新增的字段。
- [ ] `executor_ref_snapshot` 记该节点当前正式版本的全部 `executor_refs`，不记被选中的那一个。
- [ ] 入边为空（根任务）时两个 ref 字段为空元组，不报错、不跳过派发。
- [ ] 新增测试：有入边的节点两个字段都非空且形状正确、根任务两个字段为空、恢复重发与首次派发载荷一致；第一项在修复前失败。
- [ ] 既有测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 两个 ref 字段的形状由 `ai4-g5fx` 定死（`tuple[tuple[str,str], ...]`），本票不改契约，只填值。第二位的数据源由 `ai4-br61` 补。
- `upstream_source_refs` 的数据已经在 `PendingHandoff.upstream_source_refs` 里，`_evaluate_snapshot` 与 `_recompute_downstream` 都已写入。优先直接复用，不要再从快照算一遍——两份算法迟早会漂移。
- `_publish_dispatch` 走的是恢复路径，手上只有 `HandoffDispatch` 与 `PendingHandoff`，没有当时的快照上下文。若无法原样复原，就按当前正式快照重算，但必须在注释里写明这是「重发时按当前快照取」，而不是「复原当时的快照」。
- 与 `ai4-7uxz` 的交界：那张票负责「选中谁」并填 `executor_ref_snapshot`，本票负责「依据哪些版本」。`executor_ref_snapshot` 的验收在两张票里都出现，实现时只做一次，另一张改为引用，不要各写一份。

## 依赖与未决

1. **`dependency_edge_version_refs` 的第二位由 `ai4-br61` 提供。** 文档（`docs/data-flow/message-queue.md` 第 318-323 行）要求 `{logical_id, version_id}`，但 `DependencyEdgeDoc` 只有扁平的 `edge_id`——`edge_id` 在 `ai4-edrp` 的投影里就是 `logical_id`，边的 `version_id` 投影时被丢掉了。`ai4-br61` 补 `edge_version_id` 字段，本票 `deps` 因此包含它。
2. 在 `ai4-br61` 关闭前本票不应开工，否则第二位只能塞占位值。若因排期必须先做，就先只填 `upstream_source_refs` 与 `executor_ref_snapshot`，`dependency_edge_version_refs` 保持空元组并在代码注释指向 `ai4-br61`——**不要填假数据**。
3. 与边的四个判定字段（`dependency_kind`、`activation_condition`、`required_outputs`、`blocks_until`）无关。那条链是判定逻辑扩充，需要独立决策票，目前尚未建立。
