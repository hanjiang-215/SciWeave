---
id: ai4-roow
status: open
deps: [ai4-jckq]
links: [ai4-v869, ai4-jckq]
created: 2026-10-27T04:00:57Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-v869
tags: [enhancement, ready-for-agent, sciencepal, mapping, agent]
---
# SciencePal 执行报告回写地图：草稿、候选与进度两条轨道

外部 harness 完成 SciencePal 执行后，把 ExecutionReport 写入中央草稿箱；TaskNode Owner 一审后由人提交候选，Project Owner 正式化。地图只按路线变更更新；运行状态作为投影，不写进 TaskNode 版本对象。

## Design

报告契约：task_node_id、execution_id、status、sciencepal.run_id、inputs/artifacts sha256、逐条 acceptance、route_change、limitations。没有 run_id 或产物哈希不得写 completed。

草稿：create_draft(namespace=mapping, kind=mapping_change, payload={report, proposed_change_set})；不改草稿箱的 kind 白名单。

候选：候选基准用交接消息的 trigger_revision_id；地图前进后提交得到 stale_base 是正确行为，重新取基准再提交。

进度两条轨道：L0 只在正式化时更新；L1 候选带 progress 快照；L2 运行投影另立服务，本票不做。

权限：harness token 只开 read；candidate_submit 留给人/PO；formalize 永不下放。

## Acceptance Criteria

- 一份真实 SciencePal run 的 ExecutionReport 能写入草稿箱并读回（draft_id、payload 完整）。
- 一审接受后，用报告里的 proposed_change_set 提交候选并正式化，正式图出现预期变化（T4）。
- 报告缺产物或哈希不符时不得写 completed；失败报告保留 run_id 与错误码。
- 审计可关联 execution_id、run_id、draft_id、candidate_id、formal_revision_id。
- 文档明确 L0/L1 边界，不把运行状态写进 TaskNode 版本对象。
