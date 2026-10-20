---
id: ai4-91tk
status: open
deps: [ai4-7xtf, ai4-vczt]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, implementation]
---
# Wiki 正式内容与资源引用查询纵向实现

在 Wiki 正式化前置规格确定的存储与查询权威规则下，实现 LLM-Wiki 正式内容读取：通过治理记录确定当前 Formal WikiRevision，并读取精确版本正文和该版本拥有的 Resource Reference；正式查询不得读取候选内容。资源引用的当前资格状态按精确 ResourceVersion ID 从资源审核记录读取，不能代替或改写引用目标。

## Design

遵循 [`LLM-Wiki 内容模型`](../docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md)、[`Wiki 候选治理记录模型`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md)、[`Wiki Proposal 与 Merge Request Buffer 生命周期`](ai4-zewm.md) 及 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)。实现中保留 Wiki 与 Mapping 各自独立的 MCP、存储和审计边界；引用只解析到精确 WikiRevision 或 ResourceVersion，不自动跳到“最新版本”。对于 ResourceVersion 引用，当前资格提示来自对应精确版本的追加式资源审核决定；资格撤回不能使历史引用改指或失效。

## Acceptance Criteria

- [ ] 普通读取仅返回规格确认的当前 Formal WikiRevision 及其完整正文/结构化引用。
- [ ] 每条引用精确解析到既有 WikiRevision 或 ResourceVersion；目标失效时保留目标 ID 并按规格展示，不自动改指其他版本。
- [ ] 资源引用按精确 ResourceVersion ID 呈现当前资格状态和适用限制；撤回/拒绝只作状态提示，不改写历史正式引用或切换到其他版本。
- [ ] 候选、未批准、待审核或正式化未完成内容不通过普通正式查询暴露。
- [ ] 无正式版本、存储指针不一致或精确版本不可读均按 Wiki 规格返回明确不可用/需对账结果，不静默回退。
- [ ] 使用临时/隔离测试数据覆盖成功、精确引用、候选隔离及异常场景；运行配置不硬编码部署路径或端口。
