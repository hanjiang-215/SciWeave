---
id: ai4-br61
status: open
deps: [ai4-edrp]
links: [ai4-9wji, ai4-edrp, ai4-te1v, ai4-10ja]
created: 2026-10-26T12:44:01Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-p5f3
tags: [implementation, centre-control, coordinator, adapter]
---
# DependencyEdgeDoc 补齐边的版本号投影

## What to build

`DependencyEdgeDoc` 现在只有 `edge_id`，没有边的 `version_id`。TerminusDB 的 `DependencyEdge` 文档里两者都有（`logical_id` 与 `version_id`，`@id = "DependencyEdge/<version_id>"`），投影时把 `version_id` 丢了。

这一个缺失挡住了两件事：

1. `ai4-9wji` 要填 `dependency_edge_version_refs`，元素形状是 `(logical_id, version_id)`，第二位没有数据源；
2. 文档 `docs/data-flow/message-queue.md` 第 318-323 行把该字段渲染成 `{logical_id, version_id}`，与实现不一致。

本票只补投影，不改判定逻辑，不改派发行为。

## Acceptance Criteria

- [ ] `DependencyEdgeDoc` 新增 `edge_version_id: str`，与既有 `edge_id` 并列。
- [ ] `ai4-edrp` 的适配器把 TerminusDB 边的 `version_id` 投影进新字段，`edge_id` 仍取 `logical_id`。
- [ ] 新字段是必填，不给默认值：默认值会让「适配器忘了投影」和「边版本号确实是空」混为一谈。
- [ ] 固定 fixture 文档的单元测试覆盖：边的 `logical_id` 与 `version_id` 分别落到 `edge_id` 与 `edge_version_id`，两者不相等时能区分。
- [ ] `FormalSnapshot.incoming_edges()` 与 `outgoing_edges()` 的返回元素带上新字段，既有调用点无需改动。
- [ ] 既有测试全部通过；`ai4-edrp` 的 fixture 需要同步补上新字段。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- **命名用 `edge_version_id` 而不是 `version_id`。** 同一个 dataclass 里已经有 `source_version_id` 与 `target_version_id`，裸 `version_id` 会被读成「边的版本」还是「某个节点的版本」取决于读者心情。`edge_id` 已经带了 `edge_` 前缀，跟上它。
- 这个字段与 `ai4-edrp` 明确丢弃的四个判定字段（`dependency_kind`、`activation_condition`、`required_outputs`、`blocks_until`）**不是同一件事**。那四个属于判定逻辑扩充，需要独立决策票；本票补的是文档里已经存在、只是投影时漏掉的稳定字段，没有判断成分。
- 顺序上本票要等 `ai4-edrp` 的适配器落地，因为投影代码在那边。若 `ai4-edrp` 尚未开工，可以先改 dataclass 与测试（它们是纯契约），适配器那段跟着 `ai4-edrp` 一起做。
- 完成后 `ai4-9wji` 的 `dependency_edge_version_refs` 就两个位置都有数据源了，不再有占位值问题。

## 与判定字段的关系

`ai4-te1v` 规定 `dependency_kind` 的四种取值要分别处置（`blocking` 按条件放行、`information` 只产生通知事实、`conditional` 不可判定时转人工、`alternative` 按组记录），并要求「不允许把任何 `dependency_kind` 一律当作全部上游完成即放行」。当前 `coordinator` 只按上游完成事实判定。

补齐这条链需要：投影四个字段 → 按 `dependency_kind` 分支判定 → 补 `waiting_reason`。这是判定逻辑扩充，`ai4-te1v` 与规格都写明「需要独立决策」，**不在本票范围**，也不在 `ai4-9wji` 范围。目前这张决策/实现票尚未建立，是已知缺口。
