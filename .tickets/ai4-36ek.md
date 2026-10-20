---
id: ai4-36ek
status: closed
deps: []
links: []
created: 2026-10-17T01:55:57Z
type: grilling
priority: 1
assignee: hanjiang
parent: ai4-ru15  # 动态科研协作平台需求地图
tags: [wayfinder:grilling, wiki, proposal, ai4science]
---
# Wiki Buffer 提交单位：单文档、文档加引用还是完整 ChangeSet

## Question
LLM-Wiki 的端侧 Agent 通过 Wiki MCP 向 Wiki Buffer 提交时，最小治理对象应是什么：单个 WikiDocument、一个 WikiDocument 及其 Resource Reference 变更，还是包含多个文档与引用变更的完整 Wiki ChangeSet？需要结合 WikiDocument/WikiRevision 的不可变版本、Resource Reference 的一致性、Proposal 的整体审核与正式化、冲突检测、拒绝和重试，确定提交边界、原子性、幂等性和一个 Proposal 可包含的变更范围。只讨论 LLM-Wiki 内部治理，不涉及 Research Mapping，也不进入 API 或数据库实现。

## Acceptance Criteria
明确 Wiki Buffer 的最小提交单位及其包含的对象；明确文档正文与 Resource Reference 是否必须同提交；明确多个文档变更是否必须通过 ChangeSet/Proposal 组合；明确提交原子性、重复提交、拒绝后重提和冲突的产品规则；结论能直接约束后续 Wiki 领域模型与 MCP 边界。

## Answer
经确认，Wiki Buffer 的最小提交单位采用“单个文档变更单元”（Wiki Document Change Unit），而不是裸的 WikiDocument，也不是完整的跨文档 Wiki ChangeSet。

- 每个单元针对一个稳定的 WikiDocument logical_id，包含一个新的不可变 WikiRevision，以及该版本正文所需的全部 Resource Reference 增、删、改关系。正文和其引用关系作为一个一致性边界接纳，不能先接纳正文再补齐引用。
- 资源本体、ResourceVersion 或 RawArtifact 的独立治理变化不被强行塞入文档变更单元；它们作为独立资源变更提交，由对应的资源审核人处理。文档单元只声明和修改该文档拥有的引用关系。
- 一个 Wiki Proposal 可以聚合多个文档变更单元，也可以包含独立的资源引用变更，但 Proposal 是上层审核和正式化单元，不改变 Buffer 的最小接纳边界。Proposal 默认整体接纳或整体拒绝，并只影响 Wiki TerminusDB。
- 同一逻辑 WikiDocument 的每个 Buffer 单元必须记录提交者、提交标识、基于的当前 Formal WikiRevision，以及内容和引用关系的完整摘要，用于冲突检测和审计。允许从同一 Formal WikiRevision 派生多个并行 Buffer/Proposal，但每个单元必须进入隔离的候选分支，不能覆盖其他提交者的候选内容。
- 重复提交使用提交标识或内容摘要幂等处理：内容、基准版本和提交标识相同的重试返回原单元；内容不同的并行单元可以继续进入独立候选，但在正式化前必须经过冲突检测，不能直接覆盖已有候选。
- 被拒绝的单元保留原记录和拒绝原因。重新提交必须创建新的提交单元，基于最新正式版本或明确的修订来源，不修改被拒绝单元。
- Buffer 接纳只表示通过第一阶段的结构、归属和一致性审核；之后才允许将该单元纳入 Proposal 对应的 candidate branch，形成 WikiRevision 草稿。它不表示正式批准，也不改变 Formal WikiRevision。

该决议约束后续 Wiki 领域模型：需要分别表达文档变更单元、Proposal 聚合、文档版本、引用关系和资源自身变更；正式查询仍只读取 Formal WikiRevision 与正式 Resource Reference。

## Review conclusion (2026-10-18)

最小 Buffer 单元仍是单个文档及其一致的引用关系；多个单元才聚合为 Proposal。为与后续统一治理保持一致，可以从同一 Formal WikiRevision 派生隔离的并行候选，但任何候选都不能覆盖另一个候选，正式化只能选择一个完整方案。该后续 Wiki 规则不扩大首版 Research Mapping 范围。
