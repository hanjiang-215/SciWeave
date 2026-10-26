---
id: ai4-quvy
status: open
deps: []
links: []
created: 2026-10-26T16:25:53Z
type: task
priority: 2
assignee: hanjiang
parent: ai4-te1v
tags: [implementation, centre-control, coordinator, domain]
---
# DependencyEdgeDoc 补齐 dependency_kind 等四个判定字段

DependencyEdgeDoc 只有 edge/source/target 五个扁平字段，缺 dependency_kind、activation_condition、required_outputs、blocks_until。四者在 candidate_submission.py 中是必填，coordinator 目前只能按「全部上游完成即放行」判定，与 ai4-te1v 规定的 dependency_kind 首版口径不符（information / blocking / conditional / alternative 处置不同）。ai4-edrp 的适配器按范围控制故意不投影这四项，本票承接判定逻辑与投影。

## Acceptance Criteria

- [ ] DependencyEdgeDoc 增加 dependency_kind、activation_condition、required_outputs、blocks_until 字段，命名与 research-map 文档一致。
- [ ] adapter_snapshot.py 投影这四个字段，并删除「故意不投影」的注释。
- [ ] 条件判定按 ai4-te1v 的 dependency_kind 口径实现，不再一律「上游全完成即放行」。
- [ ] 新增测试覆盖四种 dependency_kind 的放行/不放行判定。
- [ ] 既有测试全部通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

