---
id: ai4-hkdz
status: in_progress
deps: []
links: []
created: 2026-10-18T15:06:41Z
type: task
priority: 1
assignee: zhanyunfei
parent: ai4-56iu  # Wiki 持久化模型分支
tags: [wayfinder:grilling]
---
# Wiki 候选治理 SQLite 结构化记录模型

定义 Wiki 领域自己维护的 SQLite 候选提交与治理元数据，不与 Research Mapping 的记录混用。

## Design

规范文档：[`docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md)。以下领域字段、关系、状态与约束是本工单的交付内容，不规定 SQLite DDL、ORM、API 或跨存储事务实现。

### 记录边界

- 所有治理记录归属 Wiki 治理上下文，以 `wiki_domain_id` 标识；Wiki 业务 ID 在本领域唯一且不可复用。
- SQLite 保存治理事实、状态、审计索引和 TerminusDB 对象的精确标识；不保存 Wiki 正文、资源本体或候选内容。候选正文及历史由 LLM-Wiki Store 持有。
- 不与 Research Mapping 记录建立强关系；`source_task_id` 等跨域标识仅为带领域语义的弱引用。
- SQLite/TerminusDB 正式化成功条件、失败恢复和跨存储权威语义由 `ai4-azx2` 决定。

### 对象、字段与关系

- **WikiBufferSubmission**：`submission_id`、`wiki_domain_id`、提交者/提交时间、`acceptance_status`、审核者/审核时间、处置原因、可选 `source_task_id`。状态沿用 `draft`、`submitted`、`accepted`、`rejected`、`revised`。接纳后至多关联一个 WikiProposal；Proposal 可收纳多个已接纳 Submission。
- **WikiProposal**：`proposal_id`、领域 ID、`status`、`base_formal_revision_id`、candidate TerminusDB Store/branch 标识、创建者/时间。状态沿用 `draft`、`candidate`、`merged`、`rejected`、`not_selected`、`abandoned`。Proposal 拥有候选分支及其 CandidateCommit。
- **WikiCandidateCommit**：内部记录 ID、Proposal ID、Store/branch、不可变 `commit_hash`、可选父 hash、精确基准 Formal WikiRevision ID、可选来源 Submission、提交者/时间、结构化变更摘要。候选正文不复制进 SQLite；hash 在对应 Wiki Store 内唯一。
- **WikiMergeRequestBuffer**：`merge_request_id`、领域 ID、`status`、固定 `base_formal_revision_id`、创建者/时间、`locked_at`、审阅结果证据引用。状态沿用 `draft`、`submitted`、`conflict`、`approved`、`rejected`、`not_selected`、`merged`。MR 关联所审查的 Proposal、CandidateCommit 和精确 candidate head；锁定后 head 及审阅范围只读。
- **WikiCandidateSolution**：`solution_id`、MR ID、候选类型 `direct`/`blended`、候选 Store/branch/head commit hash、基准版本、创建者/时间、状态 `proposed`/`selected`/`not_selected`。`blended` 是方案类型，不是审批状态。方案来源关联记录来源 Proposal/Commit 及纳入、舍弃范围摘要；直接方案引用单一来源候选，blended 方案使用新的不可变候选结果。
- **WikiSourceCommitDisposition**：按 MR 和来源 CandidateCommit 记录可选拟议处置及最终处置。最终值为 `selected`、`blended`、`partially_blended`、`abandoned`；正式化成功前最终处置必须为空，成功后写定。
- **WikiAffectedObject / 审阅证据**：受影响对象按 CandidateCommit 记录对象类型、稳定对象 ID、变更类别和受影响字段；对象类型限 WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact、Resource Reference。Diff/影响分析摘要或精确引用、证据类型及生成者/时间关联到 MR、方案或 CandidateCommit，不保存正文副本。
- **WikiFormalizationResult**：关联 MR、所选完整方案、批准 AuditEvent、结果状态及完成时间；成功时关联产生的 Formal WikiRevision ID 和正式 TerminusDB commit hash。结果状态词汇、失败/处理中状态的权威含义及恢复规则由 `ai4-azx2` 决定。
- **WikiAuditEvent**：追加式记录事件 ID、领域、时间、操作者/类型、操作、目标类型/稳定 ID、前后状态、结果/原因，并可关联 Submission、Proposal、MR、方案、CandidateCommit、正式版本和正式化结果。更正以新事件表示。
- **WikiNotification**：通知 ID、领域、接收者、类型、稳定目标类型/ID、创建时间、投递状态，以及可选投递时间、失败信息和外部投递引用；不定义消息队列实现。

### 唯一性、状态与关系约束

1. Wiki 业务 ID 在各自 `wiki_domain_id` 内唯一；CandidateCommit hash 和正式 commit hash 在对应 TerminusDB Store 内唯一。
2. 已接纳 Submission 才能关联 Proposal；一个 Submission 至多归属一个 Proposal。每个 CandidateCommit 属于一个 Proposal，其内容不可变。
3. 一个 MR 固定一个基准 Formal WikiRevision；每个锁定 head 必须精确指向已记录的 CandidateCommit。锁定后不得移动 head 或在所审范围内继续写入。
4. 一个 MR 最多选择一个完整 CandidateSolution，最多产生一个成功 FormalizationResult；成功结果恰关联一个 selected 方案、一个批准 AuditEvent、一个 Formal WikiRevision ID、一个正式 commit hash 和完成时间。
5. 同一来源 CandidateCommit 在同一 MR 中最多有一条最终处置，且最终处置仅在正式化成功后写定。Rejected、not_selected、失败候选及其审计历史保留。
6. Submission 状态归 Submission；Proposal 状态归 Proposal；MR 状态归 MR；方案的选择状态与类型分离；来源处置归 MR 与来源 CandidateCommit 的关联；通知投递状态归 Notification。状态变化追加 AuditEvent，不以当前状态替代历史。
7. 方案来源、受影响对象、证据、审计及通知均以稳定 ID 关联，不以标题或可变定位为键。不得从 Wiki 治理记录建立 Mapping 强外键。

### 场景校验

接纳流程可沿 Submission → Proposal → CandidateCommit 追溯；提交 MR 后可还原精确基准和锁定 head；direct/blended 完整方案及各来源可重建；PO 选择/驳回留下独立审计事件；只有成功正式化才写定来源处置并关联确切 Formal WikiRevision；通知记录能追踪投递结果。普通正式查询不读取候选或治理 SQLite 中的正文，因为正文只由 LLM-Wiki Store 持有。

## Question

Wiki 领域的 SQLite 治理记录需要哪些具体对象、字段和约束，以关联 Wiki Proposal、TerminusDB commit/hash、基准 Formal WikiRevision、影响文档/资源、候选混合来源、PO 处置及正式化结果？

## Notes

治理语义与 Research Mapping 可相同，但本票只定义 Wiki 自己的记录模型和对象引用。SQLite 数据库文件可共享或分离属于后续实现选择；本票要求至少保持领域表/记录结构的逻辑隔离。

## Acceptance Criteria

- [x] 明确 Wiki SQLite 治理对象的字段与彼此关系。
- [x] 明确各状态的归属、候选方案类型与审批状态的区别，以及唯一性/不可变约束。
- [x] 可追溯来源提交、候选方案、PO 决策、正式 WikiRevision 和通知，且不与 Mapping 强关系混用。

## Progress

用户已批准领域模型；字段、关系、状态、约束和场景校验已写入本工单及关联设计文档。书面规格现等待用户复核，复核前工单保持 `in_progress`。
