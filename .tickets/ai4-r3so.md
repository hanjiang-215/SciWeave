---
id: ai4-r3so
status: open
deps: [ai4-ebqx, ai4-u3rs]
links: []
created: 2026-10-16T13:42:18Z
type: grilling
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, domain-model, ai4science]
---
# Research Mapping 节点与依赖边字段模型

细化统一 Research Mapping 中 TaskNode 与 DependencyEdge 的领域字段、必填条件、字段语义、状态约束和对象间关系。只确定产品/领域模型，不进入数据库列、API 参数或代码结构。

## Acceptance Criteria

形成 TaskNode 与 DependencyEdge 的字段清单和字段语义；明确必填/可选字段、状态约束、节点与边的引用规则、版本字段和正式查询所需字段；覆盖任务规划、执行、资源引用、失败与路线演化的最小表达；不引入具体技术实现。
