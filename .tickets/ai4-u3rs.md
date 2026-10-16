---
id: ai4-u3rs
status: closed
deps: [ai4-ebqx, ai4-e257]
links: []
created: 2026-10-16T05:19:17Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, proposal, ai4science]
---
# 单一 Mapping 的草稿与正式视图模型

## Question
在不维护两张独立物理图的前提下，如何让同一张 Research Mapping 同时支持 Agent/成员提交草稿、中央 Agent 预审、负责人审核和正式调度？需要确定：TaskNode 与 DependencyEdge 的生命周期状态；正式视图、草稿视图和 Proposal 预览视图；草稿如何归属 Proposal；哪些状态可以进入正式调度；TerminusDB 每次写入立即生成 Commit 时，平台如何隔离待审核变化。暂不讨论 TerminusDB 候选分支的具体实现，该行为由独立验证票确认。

## Acceptance Criteria

明确单一物理 Mapping 的草稿/正式状态模型；明确节点和边的正式视图过滤规则；明确 Proposal 预览、负责人批准和正式调度之间的关系；明确 Agent 不能直接提升正式状态。

## Notes

**2026-10-16T12:18:56Z**

## Answer

本轮确定单一 Mapping 的草稿与正式视图模型：

- 只维护一张物理 Research Mapping；正式节点、草稿节点、正式边和草稿边共存于同一张图。
- 普通查询只读取当前最新的正式投影，不读取初始版本，也不读取 draft、submitted、rejected 或 superseded 内容；历史查询可按 FormalRevision 或时间点读取旧版本。
- 节点和边的内容创建后不可原地修改。正式对象不能直接修改；草稿对象在草稿阶段也不允许变更或再次提交新的草稿。需要修订时，必须在原草稿被批准或拒绝后，基于最新正式版本创建新的草稿版本。
- 同一逻辑对象（节点或边）同一时间只允许一个活动草稿，不允许多个并行草稿版本。一个 Proposal 可以包含多个对象的草稿，但同一对象不得同时属于多个活动 Proposal。这样优先避免并行修改和审核冲突；后续如需并行实验，另建原型决策。
- 节点和边使用 logical_id 与 version_id 区分稳定对象和具体版本，并通过 derived_from、supersedes 等关系追踪版本来源。
- 草稿提交、审核和正式化是生命周期转换；内容字段不可变，但状态可以按受控流程从 draft 转为 submitted、formal、rejected 或 superseded。
- Proposal 是多个草稿节点和边的审核单元，默认整体批准或整体拒绝，避免只正式化节点而留下未正式化的依赖边。
- 每个草稿对象记录所属 Proposal 和 base FormalRevision。若基准正式版本已经变化，则 Proposal 标记为 stale 或 conflict，不能直接批准。
- 审核人、审核时间和评语记录在 Proposal/AuditEvent；对象保存生命周期状态、Proposal 引用和正式化 Revision 引用，避免把一份整体审核信息重复复制到每个对象。
- TerminusDB 的 Commit、History 和 Diff 负责记录节点与边的数据变化；平台保存 Proposal、审核事件、base_commit、candidate_commit 和 resulting FormalRevision 的关联，不重复保存完整文字版 Diff。
- 第一阶段只要求历史追溯，不实现数据库 reset 式回滚。未来回滚应通过新 Proposal 生成新的正式 Revision，而不是移动或删除历史指针。
