# Wiki 候选治理结构化记录模型

日期：2026-10-19
关联工单：[`ai4-hkdz`](../../../.tickets/ai4-hkdz.md)
状态：领域模型已获用户批准；书面规格待复核

## 目的与边界

本设计明确 LLM-Wiki 自己维护的治理记录字段、关系、状态归属和完整性约束。字段是领域概念，不规定 SQLite DDL、ORM、API、消息队列或跨存储事务实现。SQLite 记录 Wiki 治理事实、状态、审计索引和 TerminusDB 对象的精确标识；不复制 Wiki 正文、Resource/ResourceVersion 内容或 RawArtifact 本体。Research Mapping 数据不属于本模型，也不建立强关系。

所有治理记录均属于由 `wiki_domain_id` 标识的 Wiki 治理上下文。Wiki 记录彼此以稳定业务 ID 关联。`source_task_id` 等跨域标识只作带有领域语义的弱引用；SQLite 文件是否与其他领域共用留给实现决策。候选正文和 TerminusDB 历史由 LLM-Wiki Store 持有；SQLite/TerminusDB 正式化的提交顺序、成功条件、故障恢复及不一致时的权威来源由 `ai4-azx2` 决定。

## 结构化对象与字段

### WikiBufferSubmission

代表提交者提供、等待 Wiki 首阶段接纳审核的变更请求，不是正式内容。

- `submission_id`：必填，在 Wiki domain 内唯一且不可变。
- `wiki_domain_id`：必填所属 Wiki 治理上下文。
- `submitter_id`、`submitted_at`：提交者及提交时间。
- `acceptance_status`：接纳生命周期状态；沿用 `draft`、`submitted`、`accepted`、`rejected`、`revised`。
- `reviewer_id`、`reviewed_at`、`disposition_reason`：可选审核者、审核时间及接纳/退回原因；发生审核时记录相应审核信息。
- `source_task_id`：可选 Research Mapping 任务弱引用，不是本地外键。
- 接纳后通过关联记录加入一个 WikiProposal；未接纳的 Submission 不得形成 Proposal 候选内容。

### WikiProposal

聚合已接纳的 Wiki Buffer Submission，并拥有本 Proposal 的候选分支。

- `proposal_id`、`wiki_domain_id`：必填，Proposal ID 在本领域唯一。
- `status`：Proposal 状态；沿用 `draft`、`candidate`、`merged`、`rejected`、`not_selected`、`abandoned`。
- `base_formal_revision_id`：必填，精确基准 Formal WikiRevision ID。
- `candidate_store_id`、`candidate_branch_id`：TerminusDB Store 和 Proposal 专属 candidate branch 的精确标识。
- `created_by`、`created_at`：创建者及时间。
- Submission 与 Proposal 为一对多聚合关系：一个 Proposal 可收纳多个已接纳 Submission；一个 Submission 至多关联一个 Proposal。

### WikiCandidateCommit

索引一个不可变 TerminusDB 候选提交，不复制其提交内容。

- `candidate_commit_id`、`wiki_domain_id`：SQLite 内部记录 ID 及所属领域。
- `proposal_id`：所属 WikiProposal，即该分支/提交的治理拥有者；blended 结果仍须有可审计的拥有 Proposal，其来源 Proposal 则通过方案来源关系单独记录。
- `terminus_store_id`、`branch_id`、`commit_hash`：精确 Store、分支和不可变提交标识。
- `parent_commit_hash`：可选父提交 hash。
- `base_formal_revision_id`：该候选链所依据的精确 Formal WikiRevision。
- `source_submission_id`：可选来源 Submission；提交可由一个 Proposal 中的多个已接纳 Submission 共同形成。
- `created_by`、`created_at`：提交者及时间。
- `change_summary`：结构化变更摘要，不是候选正文；摘要中的对象引用使用 Wiki 稳定 ID。

### WikiMergeRequestBuffer

代表将固定候选头交给 Project Owner 审核和正式化的请求。

- `merge_request_id`、`wiki_domain_id`：必填唯一业务 ID 及所属领域。
- `status`：MR 状态；沿用 `draft`、`submitted`、`conflict`、`approved`、`rejected`、`not_selected`、`merged`。
- `base_formal_revision_id`：必填，本次审核固定的正式基准。
- `created_by`、`created_at`、`locked_at`：创建者、创建时间及 candidate head 锁定时间。
- `review_result_reference`：可选的结构化审阅证据引用；详细 Diff/影响证据按下文的审核证据关联记录。
- MR 关联一个或多个被纳入审核的 Proposal 和 CandidateCommit，并为所审核的候选头记录 Proposal、Store、branch、精确 head commit hash。锁定后 head 与其审阅范围只读；需要修改时产生新的不可变候选，不改写已锁定记录。

### WikiCandidateSolution

代表本次 MR 中一个完整、可供 Project Owner 选择的候选方案。它不是 Wiki 正文的副本。

- `solution_id`、`wiki_domain_id`、`merge_request_id`：必填身份、领域和所属 MR。
- `candidate_type`：方案类型 `direct` 或 `blended`。`blended` 表示以新候选提交承载多个来源组合，不是审批状态。
- `candidate_store_id`、`candidate_branch_id`、`head_commit_hash`：该完整方案的精确 TerminusDB 候选分支及 head。
- `base_formal_revision_id`：必填方案基准，须与所属 MR 的固定基准一致。
- `status`：方案选择状态 `proposed`、`selected` 或 `not_selected`，与 `candidate_type` 分离。
- `created_by`、`created_at`：创建者及时间。
- 方案来源关联记录每个来源 WikiProposal 和来源 CandidateCommit，并保存该方案针对该来源保留/舍弃范围的结构化摘要。`direct` 方案指向单一来源候选；`blended` 方案须是新建的不可变候选结果，并记录其组合来源及纳入/舍弃依据。

### WikiSourceCommitDisposition

记录本次 MR 中来源提交的拟议与最终处置。它与 CandidateSolution 的方案来源关系分开，避免把备选方案中的输入误认为已经定稿。

- `merge_request_id`、`source_candidate_commit_id`：所属 MR 与被处置的来源 CandidateCommit。
- `proposed_disposition`：可选拟议处置范围/结果，仅供审核，不表示最终处理完成。
- `final_disposition`：最终值为 `selected`、`blended`、`partially_blended` 或 `abandoned`；在所选完整方案正式化成功前必须为空，成功后依据实际纳入范围写定。
- `finalized_at`：最终处置写定时间。

### WikiAffectedObject 与审阅证据

影响记录按来源 CandidateCommit 关联，不复制业务对象。

- 每条 `WikiAffectedObject` 记录：`candidate_commit_id`、Wiki 对象类型、对象稳定 ID、变更类别、受影响字段及可选影响说明。类型限于 LLM-Wiki 对象：WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact、Resource Reference。
- Diff、影响分析摘要及其精确外部引用通过审核证据关联至 MR、CandidateSolution 或 CandidateCommit，记录证据类型、摘要/精确引用、生成者和生成时间。候选正文仍只在 TerminusDB。

### WikiFormalizationResult

关联一次正式化尝试/结果及成功后产生的正式版本。状态值、跨存储权威含义、提交次序、重试和补偿由 `ai4-azx2` 规定。

- `result_id`、`wiki_domain_id`、`merge_request_id`：必填唯一记录 ID、所属领域和 MR。
- `selected_solution_id`、`approval_audit_event_id`：所选完整方案和对应批准审核事件的精确 ID。
- `result_status`、`completed_at`：正式化结果状态及完成时间；其状态词汇与跨存储含义不在本票固定。
- 成功时记录 `formal_wiki_revision_id` 和 `formal_terminus_commit_hash`。二者必须精确指向本次结果生成的正式版本和正式 Commit；失败/处理中记录是否存在及其权威语义按 `ai4-azx2`。

### WikiAuditEvent

追加式记录治理状态变化和责任链，不由当前状态字段取代。

- `event_id`、`wiki_domain_id`、`occurred_at`：必填事件 ID、领域和时间。
- `actor_id`、`actor_type`、`operation`：操作者、操作者类型及操作。
- `target_object_type`、`target_object_id`：至少一个稳定目标对象类型和 ID。
- `previous_state`、`next_state`、`result`、`reason`：适用时记录状态变化、操作结果和原因。
- 可通过稳定 ID 关联 Submission、Proposal、MR、CandidateSolution、CandidateCommit、Formal WikiRevision 和 FormalizationResult。事件不可原地改写；更正以追加事件表示。

### WikiNotification

记录对用户的通知意图和投递结果，不规定队列或传输实现。

- `notification_id`、`wiki_domain_id`：必填通知身份和领域。
- `recipient_id`、`notification_type`：接收者与通知类型。
- `target_object_type`、`target_object_id`：稳定目标对象类型和 ID。
- `created_at`、`delivery_status`：创建时间和投递状态（例如 pending、sent、failed）。
- `delivered_at`、`failure_information`、`external_delivery_reference`：可选投递时间、失败信息及外部投递引用。

## 关系与唯一性约束

1. 各类 Wiki 治理业务 ID 在各自 `wiki_domain_id` 内唯一且不可复用。所有本领域关系使用稳定 ID，不以标题、可变路径或显示名称作为键。
2. WikiCandidateCommit 必须属于一个 WikiProposal；其 hash 在对应 TerminusDB Store 内唯一。一个候选提交及其内容不可变；candidate branch 的可写/锁定控制属于 Wiki 平台治理事实。
3. 一个 MR 的基准 Formal WikiRevision 固定不变；每个被审查的候选 head 必须精确指向已记录的 WikiCandidateCommit。锁定时间存在后不得移动 MR 所审查的 head。
4. 一个 MR 最多有一个 `selected` CandidateSolution；一个 MR 最多有一个成功 FormalizationResult。每个成功结果关联恰好一个被选方案和一个批准 AuditEvent。
5. 成功 FormalizationResult 中的 Formal WikiRevision ID 在 Wiki domain 内唯一；正式 TerminusDB Commit hash 在对应 Store 内唯一。成功结果必须同时关联两者和完成时间。
6. 一个来源 CandidateCommit 在同一 MR 的来源处置记录中最多出现一次，至多有一个最终处置。最终处置只在成功正式化后写定；已拒绝、未选中或失败的候选及其审计历史继续保留。
7. 方案来源关系、受影响对象、审核证据、通知和审计关联均使用稳定对象 ID。Wiki 领域和 Research Mapping 之间不建立强外键或本地对象关系；如记录 `source_task_id`，仅为弱引用并携带其领域语义。
8. SQLite 不保存 Wiki 正文、Resource 本体、资源文件或候选提交内容；结构化变更摘要、精确对象引用和审核证据索引不构成内容副本。

## 状态归属

| 对象 | 状态/类型字段 | 语义归属 |
| --- | --- | --- |
| WikiBufferSubmission | `acceptance_status` | Submission 的接纳与退回生命周期 |
| WikiProposal | `status` | Proposal 治理状态 |
| WikiMergeRequestBuffer | `status` | MR 审核与正式化生命周期 |
| WikiCandidateSolution | `status`、`candidate_type` | 选择状态与候选类型分别保存；`blended` 只属于类型 |
| 来源提交处置 | `final_disposition` | 来源 CandidateCommit 在本次 MR 中的最终处理结果，正式化成功后写定 |
| WikiNotification | `delivery_status` | 通知投递状态 |
| WikiFormalizationResult | `result_status` | 结果记录；具体值和跨存储权威语义留给 `ai4-azx2` |

每次状态转移都追加 AuditEvent。TerminusDB Commit 本身不表示审核、选择或正式批准；候选 branch 锁定是 Wiki 治理边界，不依赖 TerminusDB 原生状态。

## 场景一致性检查

1. **提交接纳**：WikiBufferSubmission 记录提交者、时间和审核结果；接纳后恰好关联一个 WikiProposal，并可追到其 candidate commit。正文和内容版本仍由 LLM-Wiki Store 持有。
2. **提交 MR**：MR 固定基准正式版本和每个审阅候选 head 的精确 commit hash，记录锁定时间。锁定后不允许在该 MR 的审阅范围内继续追加或移动 head。
3. **直接方案与 blended 方案**：直接方案引用单一来源候选；blended 方案是新的不可变候选 head，并关联各来源 Proposal/Commit 和纳入/舍弃范围。二者的 `candidate_type` 与 `proposed` / `selected` / `not_selected` 状态分开表达。
4. **PO 选择与驳回**：AuditEvent 独立记录操作者、决策、目标方案和原因；同一个 MR 至多选择一个完整方案。被拒绝或未选中的方案仍可按稳定 ID 审计。
5. **正式化及来源处置**：FormalizationResult 关联 MR、所选方案和批准事件。只有正式化成功后，才关联确切 Formal WikiRevision、正式 TerminusDB commit hash 和完成时间，并为本 MR 各来源提交写定唯一最终处置；成功条件和失败恢复语义由 `ai4-azx2` 决定。
6. **通知**：通知按接收者、稳定目标 ID 和投递状态追踪；投递失败信息和外部引用保留在通知记录中，不改变候选或正式版本事实。

## 排除范围

本设计不规定 SQLite DDL、数据库文件如何划分、ORM/API、消息队列实现、内容复制策略、正式化跨存储事务及补偿、失败/处理中状态的权威判定、冲突检测算法或访问控制实现。这些边界不由治理记录字段模型代替；跨存储正式化语义由 `ai4-azx2` 收敛。
