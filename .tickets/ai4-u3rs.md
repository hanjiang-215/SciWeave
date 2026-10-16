---
id: ai4-u3rs
status: open
deps: [ai4-ebqx, ai4-e257]
links: []
created: 2026-10-16T05:19:17Z
type: grilling
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, proposal, ai4science]
---
# 单一 Mapping 的草稿与正式视图模型

## Question
在不维护两张独立物理图的前提下，如何让同一张 Research Mapping 同时支持 Agent/成员提交草稿、中央 Agent 预审、负责人审核和正式调度？需要确定：TaskNode 与 DependencyEdge 的生命周期状态；正式视图、草稿视图和 Proposal 预览视图；草稿如何归属 Proposal；哪些状态可以进入正式调度；TerminusDB 每次写入立即生成 Commit 时，平台如何隔离待审核变化。暂不讨论 TerminusDB 候选分支的具体实现，该行为由独立验证票确认。

## Acceptance Criteria

明确单一物理 Mapping 的草稿/正式状态模型；明确节点和边的正式视图过滤规则；明确 Proposal 预览、负责人批准和正式调度之间的关系；明确 Agent 不能直接提升正式状态。
