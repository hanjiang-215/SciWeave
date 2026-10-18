---
id: ai4-mjku
status: open
deps: []
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
parent: ai4-yl2o  # Research Mapping 持久化模型分支
tags: [wayfinder:grilling]
---
# Research Mapping 候选治理 SQLite 结构化记录模型

定义 Research Mapping 领域自己的 SQLite 候选提交与治理元数据，不与 Wiki 的记录混用。

## Design

## Question
Research Mapping 领域的 SQLite 治理记录需要哪些具体对象、字段和约束，以关联 Mapping Proposal、TerminusDB commit/hash、基准 Formal MappingRevision、受影响的 TaskNode/Dependency Edge、候选混合来源、PO 处置及正式化结果？请明确：
- TerminusDB 提交/hash、基准 Formal MappingRevision 和 Mapping 领域标识如何关联；
- 受影响 TaskNode/Dependency Edge 与字段、结构化摘要、Diff/影响分析引用如何表示；
- 原候选、混合候选、来源关系和来源提交处置如何追溯；
- `selected`、`blended`、`partially blended`、`abandoned` 等状态及其对象归属、允许转换和唯一性约束；
- PO 选择、审核事件、Formal MappingRevision 关联和提交者通知记录需要保存哪些结构化事实。

## Notes
以“正式版本前进后候选重放与冲突审核规则”的决策为前提。只确定 Research Mapping 领域记录模型与字段语义，不选具体 SQLite DDL、ORM 或消息队列产品。SQLite 文件是否与 Wiki 共用不在本票范围；本票要求领域表/记录逻辑隔离。

## Acceptance Criteria

形成 Research Mapping SQLite 治理对象与字段清单，说明关系、约束、索引需求和状态归属；能够追溯每个来源提交的基准、变更、方案、PO 决策、最终处置及正式版本。
