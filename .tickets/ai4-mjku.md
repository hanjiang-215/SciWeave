---
id: ai4-mjku
status: open
deps: []
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
parent: ai4-xup8  # Research Mapping 与 Wiki 领域数据模型和持久化规格地图
tags: [wayfinder:grilling]
---
# 候选治理 SQLite 结构化记录模型

将已确定的候选重放、混合和处置治理规则转化为 SQLite 中结构化治理记录的领域模型。

## Design

## Question
SQLite 需要以哪些记录和字段表达候选提交、审核轮次、候选方案及正式化结果？请明确：
- TerminusDB 提交/hash、基准 Formal Revision 和领域标识如何关联；
- 受影响对象/字段、结构化摘要、Diff/影响分析引用如何表示；
- 原候选、混合候选、来源关系和来源提交处置如何追溯；
- `selected`、`blended`、`partially blended`、`abandoned` 等状态及其对象归属、允许转换和唯一性约束；
- PO 选择、审核事件、正式 Revision 关联和提交者通知记录需要保存哪些结构化事实。

## Notes
以 ai4-iciy 的治理决策为前提。只确定领域记录模型与字段语义，不选具体 SQLite DDL、ORM 或消息队列产品。

## Acceptance Criteria

形成 SQLite 治理对象与字段清单，说明关系、约束、索引需求和状态归属；能够追溯每个来源提交的基准、变更、方案、PO 决策、最终处置及正式版本。
