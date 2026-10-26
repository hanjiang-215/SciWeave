---
id: ai4-fu4i
status: open
deps: []
links: []
created: 2026-10-26T16:25:47Z
type: bug
priority: 1
assignee: hanjiang
parent: ai4-10ja
tags: [implementation, centre-control, coordinator, message-queue]
---
# task_handoff_ready 未填 dependency_edge_version_refs

coordinator 发布 task_handoff_ready 时只填了 upstream_source_refs 与 executor_ref_snapshot，dependency_edge_version_refs 一直是空数组。docs/data-flow/message-queue.md 要求它是该节点在当前正式快照中的全部入边版本引用（(logical_id, version_id) 对）。根因在数据模型：adapter_snapshot.py 把 DependencyEdge 文档的 version_id 存进 DependencyEdgeDoc.edge_id，logical_id 直接丢弃，因此服务层拿不到边的 logical_id。

## Acceptance Criteria

- [ ] DependencyEdgeDoc 同时保留边的 logical_id 与 version_id，命名不再含糊。
- [ ] 两处发布点（_dispatch_ready 与 _publish_dispatch）都填 dependency_edge_version_refs。
- [ ] 单入边时仍是数组形式。
- [ ] 新增测试断言下游交接消息的 dependency_edge_version_refs 内容。
- [ ] 既有测试全部通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

