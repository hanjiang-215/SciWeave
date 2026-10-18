---
id: ai4-t5zl
status: open
deps: []
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
parent: ai4-yl2o  # Research Mapping 持久化模型分支
tags: [wayfinder:grilling]
---
# Research Mapping TaskNode 与 Dependency Edge 持久化字段模型

基于已关闭的 Research Mapping 节点/依赖边字段模型和治理规则，将产品领域概念映射为可持久化的具体对象模型。

## Design

## Question
Research Mapping 的 TaskNode、Dependency Edge、版本和 Formal MappingRevision 在 TerminusDB 中分别需要哪些具体字段、标识和关系？请明确：
- TaskNode 与 Dependency Edge 的稳定逻辑身份、不可变版本身份及来源/替代关系；
- 节点内容、依赖语义和运行投影哪些属于持久化领域数据，哪些不应存入图对象；
- candidate/formal 版本如何关联到 Proposal、Formal MappingRevision 和底层 TerminusDB Commit；
- 字段约束、必填性、引用完整性与版本不变量。

## Notes
以 ai4-r3so、ai4-xrxw、ai4-2alw 的已决结论为前提；这是具体领域持久化模型决策，不讨论 API 或代码实现。

## Acceptance Criteria

产出 TaskNode、Dependency Edge、版本和正式版本关联的字段/关系清单；明确每个字段含义、约束与存储归属；通过代表性新增、修改、废弃和正式化场景检查模型一致性。
