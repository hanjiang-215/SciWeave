---
id: ai4-ysr9
status: closed
deps: []
links: []
created: 2026-10-28T20:21:05Z
type: bug
priority: 1
assignee: hanjiang
---
# 看板任务状态无回写映射，status 恒 unknown

mapping 看板唯一状态来源是映射节点文档自身 execution_status/task_status/status 字段（dashboard_source.py:81 只读），而执行事实存放在 gateway execution_records 与 coordinator completed_fact，无任何写入者（B7）。故看板任务一律 unknown、completed 恒 0。

## Design

推荐方案 2（只读聚合，不改正式映射不可变语义）：dashboard_source._task_status 按 task_node_version_ref 关联 execution_records/completed_fact 推导状态。备选方案 1（新增执行状态投影）需扩展 mapping schema。

## Acceptance Criteria

看板 succeeded/completed 计数与执行事实一致；不再出现恒 unknown；不改写正式映射文档。


## Notes

**2026-10-29 / hanjiang**

已实现并验证（feat(mapping): derive task status from execution facts）：
- 新增只读 ExecutionStatusResolver，按 (mapping_domain_id, task_node_version_ref)（从 usiness_key 解析）关联网关 execution_records 推导任务状态。
- _task_status 在节点自身无状态字段时回退到 resolver；uild_mapping_fragment/server 支持注入；由 SCIWEAVE_MAPPING_EXECUTION_DB 开启，不改写入正式映射（方案 2，只读聚合）。
- 测试：research-map 137 passed（含 2 项新增）。
