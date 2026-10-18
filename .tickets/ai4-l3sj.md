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
# LLM-Wiki 文档与资源引用持久化字段模型

明确 LLM-Wiki 正式文档、资源引用和候选版本在 TerminusDB 中的具体领域存储模型。

## Design

## Question
WikiDocument、WikiRevision、Resource、ResourceVersion、Resource Reference 及其 Formal WikiRevision/candidate 关联，分别需要哪些具体字段、标识和关系？请明确不可变版本、引用完整性、资源版本定位、治理状态与正式查询边界。

## Notes
以 ai4-saug、ai4-36ek、ai4-2sdn、ai4-zewm 和 ai4-iciy 的已决领域规则为输入；保持 Wiki 与 Research Mapping 的存储和治理记录隔离。此票讨论领域持久化模型，不讨论 API 或实现代码。

## Acceptance Criteria

形成 Wiki 领域持久化对象、字段、关系和约束清单；明确正式/候选版本边界、资源引用指向和历史可追溯要求；以文档修改、引用变化和候选正式化场景检查模型完整性。
