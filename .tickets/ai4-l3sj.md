---
id: ai4-l3sj
status: open
deps: []
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
parent: ai4-56iu  # Wiki 持久化模型分支
tags: [wayfinder:grilling]
---
# LLM-Wiki 内容模型与资源引用字段设计

明确 Wiki 内容对象、页面元数据和资源引用的具体领域字段、关系与约束，供后续实现规格使用。

## Design

## Question
WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 与 Resource Reference 分别应承载哪些内容字段和关系？请明确：
- Wiki 文档分类、稳定身份、标题/描述/正文及来源信息分别属于哪个对象；
- 页面元数据与版本内容如何组织，哪些字段是文档级信息、哪些属于单个 WikiRevision；
- Resource、ResourceVersion、RawArtifact 和 Resource Reference 的内容职责及引用关系；
- 正式引用如何指向不可变 WikiRevision 或 ResourceVersion，以及字段约束和引用完整性要求。

## Notes
Wiki 的 Proposal、candidate branch、candidate Commit、Formal WikiRevision 指针和审核生命周期已经由既有决策确定：沿用统一提案治理语义，同时保持 Wiki 领域隔离。本票只决定内容对象与资源引用的字段模型，不重新讨论版本治理状态机、候选正式化规则、API 或代码实现。

## Acceptance Criteria

形成 Wiki 内容对象、版本正文/元数据、资源对象与资源引用的字段和关系清单；说明字段定义、归属、约束和正式版本引用方式；以新增文档、修订内容、变更引用和正式查询场景检查模型一致性。
