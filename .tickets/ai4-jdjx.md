---
id: ai4-jdjx
status: open
deps: [ai4-7xtf, ai4-txhf, ai4-vczt]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, implementation]
---
# Wiki 候选审阅、正式化与恢复纵向实现

实现 LLM-Wiki 候选差异/冲突审阅、Merge Request Buffer 与 Project Owner 决策，随后按 Wiki 前置规格完成 Formal WikiRevision 激活及跨存储失败恢复。

## Design

对固定 Wiki candidate head 和 base Formal WikiRevision 做差异/冲突预检，覆盖文档、资源引用、Entity/Concept 关系和共享引用。Merge Request Buffer 引用完整方案，不重复承载正文。Project Owner 仅在每个资源引用均有针对精确版本、仍有效且使用范围适配的独立资源批准，且文档/引用审核已完成后进行正式发布审核；Owner 决定不能替代任何一项审核。正式化状态和跨存储成功边界遵循 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)、[`Wiki 候选治理记录模型`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md) 和 [`Wiki Proposal 与 Merge Request Buffer 生命周期`](ai4-zewm.md)，不能借用 Mapping 的专属恢复规则替代。

## Acceptance Criteria

- [ ] 差异/冲突检查绑定精确 candidate head 和 base Formal WikiRevision；基准前进或候选变化时不可按旧预览直接批准。
- [ ] Merge Request Buffer、Owner 选择/驳回、理由和审计事件可被结构化追踪；不同候选和历史 Commit 不被改写。
- [ ] 资源资格检查发生在 Project Owner Formal Publication Review 前，并区别于 Wiki Submission 接纳和文档/引用审核；三类决定分别留有可追溯证据。
- [ ] 若资源批准在 Project Owner 审核后、SQLite 激活前被撤回或变更，激活被阻止；重新取得适用资源批准后须重新取得 Owner 批准并使用新正式化操作身份。
- [ ] 只有完整获批方案可进入 Wiki 正式化；普通查询在唯一生效点前保持此前正式版本。
- [ ] 按 Wiki 前置规格覆盖各存储部分失败、未知结果、幂等重试、读回对账/恢复及通知失败。
- [ ] 自动化/集成验证覆盖无冲突、有冲突、驳回、正式化成功及至少一个跨存储失败恢复路径。
