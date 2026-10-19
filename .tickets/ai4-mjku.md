---
id: ai4-mjku
status: closed
deps: [ai4-xrxw, ai4-t5zl, ai4-2alw, ai4-3nru]
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
assignee: zhanyunfei
parent: ai4-yl2o  # Research Mapping 持久化模型分支
tags: [wayfinder:grilling]
---
# Research Mapping 候选治理 SQLite 结构化记录模型

定义 Research Mapping 领域自己的 SQLite 候选提交与治理元数据，不与 Wiki 的记录混用。

## Design

书面规格：[`docs/superpowers/specs/2026-10-19-research-mapping-candidate-governance-record-model-design.md`](../docs/superpowers/specs/2026-10-19-research-mapping-candidate-governance-record-model-design.md)。以下为 Research Mapping 领域自己的治理记录模型，不规定 SQLite DDL、ORM、API、消息队列或跨存储事务实现。

### 记录边界

- 所有记录以 `mapping_domain_id` 标识 Research Mapping 治理上下文；业务 ID 在本领域内唯一且不可复用。
- SQLite 保存提交、Proposal、candidate branch/head、Commit/hash、审核、Formal MappingRevision 关联、通知和审计事实；不保存 TaskNode/DependencyEdge 正文、候选图快照或资源本体。
- TerminusDB 保存候选/正式图内容和 Commit 历史；Commit/hash 是存储身份，不代表 Project Owner 批准。
- Research Mapping 与 LLM-Wiki 记录逻辑隔离；`source_task_id`、资源版本 ID 等跨域关联只作带领域语义的弱引用。
- 首版使用单领域、单候选路径；字段预留未来 `blended` 和并行来源，但不得在首版绕过既有 Proposal 审核。
- FormalizationResult 的成功判定、提交顺序、部分失败、重试/补偿和不一致查询权威由 `ai4-azx2` 决定，本票只固定记录入口。

### 对象与字段

- **MappingBufferSubmission**：`submission_id`、`mapping_domain_id`、`submitter_id`、`submitter_type`、`submitted_at`、`acceptance_status`、`base_formal_revision_id`、`change_set_id`、`change_summary`、`target_object_refs`、可选 `source_task_id`/`source_execution_record_id`、审核者/时间/原因和可选 `proposal_id`。只有 `accepted` 的 Submission 才能关联 Proposal，一个 Submission 至多归属一个 Proposal。
- **MappingProposal**：`proposal_id`、领域 ID、`status`（`draft`/`candidate`/`mr_ready`/`stale`/`conflict`/`merged`/`rejected`/`abandoned`）、`base_formal_revision_id`、candidate Store/branch、当前 head Commit/hash、创建/放弃信息和影响摘要。候选基准创建后不可改写。
- **MappingCandidateCommit**：内部记录 ID、Proposal ID、Store/branch、不可变 `commit_hash`、可选父 hash、精确基准 Formal MappingRevision、可选来源 Submission、创建者/时间和结构化 `change_summary`。正文不复制进 SQLite。
- **MappingMergeRequestBuffer**：`merge_request_id`、领域 ID、`status`（`draft`/`submitted`/`conflict`/`stale`/`approved`/`rejected`/`merged`）、固定基准、精确 candidate head、创建/锁定时间、所审 Proposal 和审阅证据引用。锁定后 head 与审阅范围只读；`approved` 不等于已经产生 Formal MappingRevision。
- **MappingCandidateSolution**：`solution_id`、MR ID、`candidate_type`（首版仅 `direct`，预留 `blended`）、候选 Store/branch/head、基准版本、`status`（`proposed`/`selected`/`not_selected`）、创建者/时间和方案摘要。`blended` 是方案类型，不是审批状态。
- **MappingSourceCommitDisposition**：MR 与来源 CandidateCommit、拟议处置、最终处置、范围摘要和时间。最终值为 `selected`、`blended`、`partially_blended`、`abandoned`，只有正式化成功后才写定。
- **MappingAffectedObject**：按 CandidateCommit 索引对象类型（`TaskNode`/`DependencyEdge`/`FormalMappingRevision`）、稳定逻辑 ID、版本 ID、变更类别、受影响字段和影响摘要，不复制图正文。
- **MappingReviewEvidence**：证据 ID、所属治理对象、证据类型（`diff`/`impact_preview`/`dry_run`/`approval`/`validation`）、摘要或稳定定位、生成者/时间和可选校验信息。
- **MappingFormalMappingRevision**：`formal_revision_id`、领域 ID、Store/正式 branch/正式 `commit_hash`、父正式版本、来源 Proposal/MR、批准 AuditEvent、发布者和发布时间。它是产品层正式版本身份，与 TerminusDB Commit 一一精确关联但不等同。
- **MappingFormalizationResult**：MR、所选方案、批准事件、尝试序号/时间、结果状态、正式版本/Commit 关联、错误摘要和恢复引用。结果状态及跨存储权威由 `ai4-azx2` 收敛；允许保留多次有序尝试，但一个 MR 最多一个最终成功结果。
- **MappingAuditEvent**：追加式事件 ID、领域、时间、操作者/类型、操作、目标类型/ID/版本、前后状态、结果/原因及可选 Submission、Execution Record、Proposal、Commit、MR、方案、FormalRevision、证据引用。
- **MappingNotification**：通知 ID、领域、接收者、通知类型、稳定目标 ID、创建/投递状态、投递时间、失败信息和外部投递引用；不定义消息队列实现。

### 关系、唯一性和状态约束

1. CandidateCommit 必须属于一个 Proposal；hash 在对应 TerminusDB Store 内唯一，Commit 和图内容不可变。
2. Proposal、MR、CandidateSolution 的 `base_formal_revision_id` 必须一致；正式版本前进后旧候选不得静默重放，必须进入 `stale`/冲突阻断或从新基准重建。
3. MR 固定一个 candidate head；head 必须指向已记录 CandidateCommit，锁定后不得移动。一个 MR 至多选择一个完整 CandidateSolution，并至多产生一个最终成功 FormalizationResult。
4. 一个来源 Commit 在同一 MR 中至多有一条最终处置；拒绝、未选中、冲突和失败候选及审计历史保留。
5. `current_formal_revision_id` 在每个 Mapping 域内至多有一个当前值；正式版本记录不可覆盖或删除。
6. `MappingAffectedObject` 使用 `(candidate_commit_id, object_type, logical_id, version_id)` 追踪对象；引用旧版本的边和节点变化必须在 CandidateChangeSet 中显式出现。
7. 审计事件追加写入，更正以新事件表示；通知投递失败不改变候选或正式版本事实。
8. 不建立 Mapping 与 Wiki 的强外键；所有跨域 ID 都需要领域标识并由对应校验器解析。

### 施工前场景检查

- Submission 接纳后才能生成 Proposal/CandidateCommit；候选不进入 Formal Query。
- MR 提交前生成 Diff/影响预览并锁定 candidate head；Project Owner 驳回时保存原因和全部候选历史。
- Project Owner 批准只写入批准 AuditEvent；只有 `ai4-azx2` 定义的正式化成功条件满足后，才登记正式 Commit 和 Formal MappingRevision，并更新正式查询指针。
- 正式化中途失败必须保留审批、尝试、错误和后续恢复引用；未确认的候选不得进入正式查询。具体中间状态不在本票先行决定。
- 未来 `blended` 方案必须创建新的 CandidateCommit，记录每个来源的纳入、部分纳入或放弃范围，不能修改来源分支。

## Question

Research Mapping 领域的 SQLite 治理记录需要哪些具体对象、字段和约束，以关联 Mapping Proposal、TerminusDB commit/hash、基准 Formal MappingRevision、受影响的 TaskNode/Dependency Edge、候选混合来源、PO 处置及正式化结果？请明确：

- TerminusDB 提交/hash、基准 Formal MappingRevision 和 Mapping 领域标识如何关联；
- 受影响 TaskNode/Dependency Edge 与字段、结构化摘要、Diff/影响分析引用如何表示；
- 原候选、混合候选、来源关系和来源提交处置如何追溯；
- `selected`、`blended`、`partially blended`、`abandoned` 等状态及其对象归属、允许转换和唯一性约束；
- PO 选择、审核事件、Formal MappingRevision 关联和提交者通知记录需要保存哪些结构化事实。

## Notes

以“正式版本前进后候选重放与冲突审核规则”的决策为前提。只确定 Research Mapping 领域记录模型与字段语义，不选具体 SQLite DDL、ORM 或消息队列产品。SQLite 文件是否与 Wiki 共用不在本票范围内；本票要求领域表/记录逻辑隔离。

## Acceptance Criteria

- [x] 明确 Research Mapping SQLite 治理对象的字段、关系、状态归属和逻辑索引需求。
- [x] 明确 TerminusDB Store/branch/Commit、基准 Formal MappingRevision、候选头和领域标识的精确关联。
- [x] 明确来源提交、direct/blended 方案、来源处置、受影响对象、PO 决策、Formal MappingRevision、通知和审计的追溯链。
- [x] 明确唯一性、不可变性、锁定、基准过期、拒绝/冲突/失败保留和跨领域弱引用约束。
- [x] 通过首次提交、候选审核、驳回、正式化失败、正式版本前进和未来 blended 方案场景检查模型一致性。

## Answer

Research Mapping 治理库采用“候选内容在 TerminusDB、治理事实在 SQLite”的分工：Submission → Proposal → CandidateCommit → Merge Request Buffer → CandidateSolution → FormalizationResult/FormalMappingRevision 的链路全部以稳定 ID 和精确 Store/branch/hash 关联。`selected`、`blended`、`partially_blended`、`abandoned` 分别属于方案类型或来源处置，不混用为审批状态；正式化失败和跨存储权威语义明确留给 `ai4-azx2`。

## Progress

字段、关系、状态、唯一性约束、逻辑索引和代表性场景已写入关联书面规格；本票达到施工前领域规格的验收条件。后续只需在 `ai4-azx2` 中决定跨存储正式化协议，不需要重做本领域记录模型。

**2026-10-19T11:10:30Z**

> *This was generated by AI during triage.*

施工前收敛完成（2026-10-19）：Research Mapping 专属 SQLite 治理记录已明确 Submission、Proposal、CandidateCommit、Merge Request Buffer、CandidateSolution、来源处置、受影响对象、Formal MappingRevision、FormalizationResult、AuditEvent 和 Notification 的字段、关系、状态归属、唯一性与索引语义。书面规格见 docs/superpowers/specs/2026-10-19-research-mapping-candidate-governance-record-model-design.md。依赖已补齐至 ai4-t5zl、ai4-xrxw、ai4-3nru、ai4-2alw；跨存储正式化仍由 ai4-azx2 决定。验收条件已全部满足。

**2026-10-19T11:21:38Z**

> *This was generated by AI during triage.*

施工前状态收敛验证（2026-10-19）：

- `git diff --check`：通过，无空白错误。
- `fer dep cycle`：通过，未发现依赖环。
- 本票验收条件均已勾选，Research Mapping 专属治理记录规格已存在并与内容模型保持领域隔离。
- 本票已关闭；正式化跨存储一致性仍由 `ai4-azx2` 单独决定。
