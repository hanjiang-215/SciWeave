---
id: ai4-txhf
status: open
deps: [ai4-7xtf, ai4-91tk, ai4-vczt]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, implementation]
---
# Wiki 文档提交与候选 Proposal 纵向实现

实现 LLM-Wiki 文档变更从端侧提交到隔离候选 Proposal 的纵向路径。接纳单元为一个 WikiDocument 变更及其完整 Resource Reference 关系；提交需基于明确的正式版本。候选可暂存指向待审资源的精确引用并显示资格状态，但未经当前有效资源批准的候选不得进入 Project Owner Formal Publication Review 或正式化。

## Design

遵循 [`LLM-Wiki 内容模型`](../docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md)、[`Wiki 候选治理记录模型`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md)、[`Wiki Proposal 与 Merge Request Buffer 生命周期`](ai4-zewm.md)，以及 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)。单个文档正文与其完整引用关系作为一致性单元接纳；一个 Proposal 可聚合多个文档单元，但不跨域修改 Mapping。候选不可覆盖其他提交者候选。资源资格记录与 Wiki 文档接纳/引用适切性审核彼此独立。

## Acceptance Criteria

- [ ] 基于正式 WikiRevision 创建一个包含完整正文和 Resource Reference 的 Buffer 单元；正文和引用关系原子接纳。
- [ ] 候选中的每个资源引用均绑定精确 ResourceVersion ID 并可显示其当前审核资格；待审/被拒/已撤回资源可留在隔离候选，但不能呈现为已批准，也不能通过提交流程进入 Project Owner 正式审核或正式化。
- [ ] 通过接纳后生成独立 Proposal/candidate branch 与不可变候选版本，并记录提交者、提交标识、正式基准及审计关联。
- [ ] 重复提交依既有幂等规则返回原单元；新内容不覆盖其他候选；非法目标、跨域对象或不完整引用被拒绝。
- [ ] 自动化测试覆盖接纳成功、引用完整性、资源审核不满足、重复提交及候选隔离。
