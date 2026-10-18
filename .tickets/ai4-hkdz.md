---
id: ai4-hkdz
status: open
deps: []
links: []
created: 2026-10-18T15:06:41Z
type: task
priority: 1
parent: ai4-56iu  # Wiki 持久化模型分支
tags: [wayfinder:grilling]
---
# Wiki 候选治理 SQLite 结构化记录模型

定义 Wiki 领域自己维护的 SQLite 候选提交与治理元数据，不与 Research Mapping 的记录混用。

## Design

## Question
Wiki 领域的 SQLite 治理记录需要哪些具体对象、字段和约束，以关联 Wiki Proposal、TerminusDB commit/hash、基准 Formal WikiRevision、影响文档/资源、候选混合来源、PO 处置及正式化结果？

## Notes
治理语义与 Research Mapping 可相同，但本票只定义 Wiki 自己的记录模型和对象引用。SQLite 数据库文件可共享或分离属于后续实现选择；本票要求至少保持领域表/记录结构的逻辑隔离。

## Acceptance Criteria

明确 Wiki SQLite 治理记录的字段、关系、状态归属和唯一性约束；能够从来源提交追溯到候选方案、PO 决策、正式 WikiRevision 和通知；不与 Mapping 领域记录混为一类。
