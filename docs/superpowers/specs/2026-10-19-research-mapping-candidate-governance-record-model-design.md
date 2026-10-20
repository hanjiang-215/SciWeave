# Research Mapping 候选治理结构化记录模型设计

- 日期：2026-10-19
- 关联工单：[`ai4-mjku`](../../../.tickets/ai4-mjku.md)
- 状态：施工前领域规格已收敛

## 目的与边界

本设计定义 Research Mapping 领域自己维护的治理记录字段、关系、状态归属、唯一性和审计追溯。SQLite 只保存治理事实、状态、审计索引以及 TerminusDB 对象的精确标识，不保存 TaskNode/DependencyEdge 正文、候选图内容、资源本体或执行结果正文。候选内容和历史 Commit 由 Research Mapping Store 持有；TaskNode/DependencyEdge 内容字段见 [`ai4-t5zl`](../../../.tickets/ai4-t5zl.md)。

本领域治理记录与 LLM-Wiki 治理记录逻辑隔离。`source_task_id`、`task_node_version_id` 等跨域关联只表达弱引用，不建立对 Wiki 表或对象的强外键。正式化的跨存储业务顺序、成功条件、部分失败可见状态、重试/补偿和不一致时的查询权威已由 `ai4-azx2` 收敛，完整语义见 [`Research Mapping 跨存储正式化一致性与失败恢复设计`](./2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md)。本设计负责提供记录这些事实所需的字段和关系，不把具体 SQL、TerminusDB Schema、API 或队列实现写入领域模型。

首版 Research Mapping 仍是单领域、单候选演示路径。字段模型预留未来并行候选、`blended` 方案和来源处置，但这些状态不能在首版绕过既有的单候选 Proposal 生命周期。

## 通用标识和持久化规则

- `mapping_domain_id`：所有治理记录的领域作用域。业务 ID 在该作用域内唯一且不可复用。
- `proposal_id`、`submission_id`、`candidate_commit_id`、`merge_request_id`、`solution_id`、`result_id`、`event_id`、`notification_id`：稳定不可变 ID；标题和分支显示名不能作为关联键。
- `terminus_store_id`、`branch_id`、`commit_hash`：精确的存储定位。hash 在对应 TerminusDB Store 内唯一；不能仅凭 branch 名称判断内容或批准状态。
- 所有状态变化追加 `MappingAuditEvent`，不通过覆盖历史事件恢复或伪造转换。
- SQLite 记录可索引图对象和摘要，但不复制正文。若审核需要详细 Diff，应保存摘要和精确证据引用，而不是把候选图快照复制到 SQLite。

## 结构化对象与字段

### MappingBufferSubmission

表示人员或 Agent 提交到 Mapping Buffer、等待 TaskNode Owner 和 Central Agent 处理的结构化变更请求。

- `submission_id`、`mapping_domain_id`：必填，领域内唯一且不可变。
- `submitter_id`、`submitter_type`、`submitted_at`：提交者身份、主体类型和时间。
- `acceptance_status`：沿用 `received`、`owner_review`、`accepted`、`rejected`、`central_pre_review`、`candidate_created`。状态只描述该提交的接纳/预审进度，不代表正式路线。
- `base_formal_revision_id`：必填的精确正式基准；初始 Mapping 创建可使用空值，但必须由领域规则明确标记为初始创建。
- `change_set_id`、`change_summary`：变更集稳定标识和结构化摘要；正文、节点完整内容和资源正文仍在候选图存储中。
- `target_object_refs`：受影响 TaskNode/DependencyEdge 的稳定逻辑 ID、版本 ID 和变更类型摘要；不能只保存标题。
- `source_task_id`、`source_execution_record_id`：可选的来源任务/执行记录弱引用，用于解释路线变更来源。
- `reviewer_id`、`reviewed_at`、`disposition_reason`：发生接纳或退回时记录审核者、时间和原因。
- `proposal_id`：可选；只有进入候选 Proposal 后才能设置，且一个 Submission 至多属于一个 Proposal。

### MappingProposal

聚合已接纳的 Submission，并拥有从一个正式基准派生的 candidate branch。

- `proposal_id`、`mapping_domain_id`：必填稳定身份。
- `status`：当前生命周期状态，使用 `draft`、`candidate`、`mr_ready`、`stale`、`conflict`、`merged`、`rejected`、`abandoned`。`not_selected` 仅作为未来并行候选扩展保留，不改变首版单候选状态机。
- `base_formal_revision_id`：必填精确正式基准；候选一旦创建不得改写基准。
- `candidate_store_id`、`candidate_branch_id`：Proposal 专属候选存储和分支标识。
- `candidate_head_commit_id`、`candidate_head_commit_hash`：当前候选头；创建 Merge Request 后固定并只读。
- `created_by`、`created_at`、`abandoned_at`：创建和放弃事实；放弃后不允许继续写入。
- `description`、`impact_summary`：面向审核的结构化说明，不替代 CandidateCommit 的精确变更摘要。

一个 Proposal 可关联多个已接纳 Submission，但每个 Submission 至多关联一个 Proposal。候选正文由 candidate branch 持有，SQLite 只索引候选头和治理关系。

### MappingCandidateCommit

索引 candidate branch 中的一个不可变 TerminusDB Commit。

- `candidate_commit_id`、`mapping_domain_id`、`proposal_id`：必填，Commit 的治理归属不可变。
- `terminus_store_id`、`branch_id`、`commit_hash`：精确存储定位；hash 在 Store 内唯一。
- `parent_commit_hash`：可选父 Commit；候选链首个提交为空或指向平台记录的候选起点。
- `base_formal_revision_id`：该候选链依据的精确 Formal MappingRevision，必须与 Proposal 基准一致。
- `source_submission_id`：可选来源 Submission；一个 Commit 可由同一 Proposal 的多个已接纳 Submission 形成，因此不把它设计成唯一外键。
- `created_by`、`created_at`：候选提交主体和时间。
- `change_summary`：新增/修改/废弃/恢复的结构化摘要，包含对象类型、逻辑 ID、版本 ID 和字段级影响；不保存正文副本。

CandidateCommit 只代表候选图存储历史，不代表 TaskNode Owner 接纳或 Project Owner 批准。

### MappingMergeRequestBuffer

代表把固定 candidate head 交给 Project Owner 进行 Diff、影响审阅和正式发布审核的请求。

- `merge_request_id`、`mapping_domain_id`：必填稳定身份。
- `status`：使用 `draft`、`submitted`、`conflict`、`stale`、`approved`、`rejected`、`merged`。`approved` 只表示 Project Owner 已批准；是否已经形成正式版本由 `MappingFormalizationResult` 记录。
- `base_formal_revision_id`：必填且固定；必须与所审 Proposal/方案的基准一致。
- `candidate_head_commit_id`、`candidate_head_commit_hash`：提交审核时固定的候选头，必须指向已记录 CandidateCommit。
- `created_by`、`created_at`、`locked_at`：创建、提交和锁定事实。
- `review_result_reference`：可选的审阅证据索引；详细 Diff、dry-run 和影响分析通过 `MappingReviewEvidence` 关联。
- `proposal_id`：首版单候选必填；未来并行候选可通过关联记录纳入多个完整方案，但一个 MR 仍只能选择一个完整方案。

`locked_at` 存在后，候选 head、祖先 Commit 和审阅范围只读；需要修改时创建新的 CandidateCommit/解决方案，不能移动已锁定的 head。

### MappingCandidateSolution

表示一个 MR 中可供 Project Owner 选择的完整候选方案。首版只允许 `direct`，但结构化记录预留未来的 `blended`。

- `solution_id`、`mapping_domain_id`、`merge_request_id`：必填。
- `candidate_type`：`direct` 或 `blended`；`blended` 表示新的候选结果组合，不是审批状态。
- `candidate_store_id`、`candidate_branch_id`、`head_commit_id`、`head_commit_hash`：该完整方案的精确候选头。
- `base_formal_revision_id`：必填，必须与 MR 固定基准一致。
- `status`：`proposed`、`selected`、`not_selected`；与 `candidate_type` 分开表达。
- `created_by`、`created_at`：方案创建主体和时间。
- `solution_summary`：方案保留/舍弃范围、冲突处理和影响摘要。

`direct` 方案引用单一来源候选；`blended` 方案必须产生自己的不可变 CandidateCommit，并通过来源关系记录每个纳入或舍弃的来源。首版不允许用 `blended` 绕过单候选审核。

### MappingSourceCommitDisposition

记录本次 MR 中每个来源 CandidateCommit 的拟议和最终处置，避免把“方案输入”误认为已完成的正式处置。

- `merge_request_id`、`source_candidate_commit_id`：必填关联。
- `proposed_disposition`：可选审核阶段建议。
- `final_disposition`：`selected`、`blended`、`partially_blended` 或 `abandoned`；成功正式化前必须为空。
- `disposition_summary`：纳入、舍弃或部分纳入的对象范围和理由。
- `finalized_at`：最终处置写定时间。

同一来源 Commit 在同一 MR 中最多有一条处置记录。最终处置只在正式化成功条件满足后写定；被拒绝、未选中或失败的候选及其历史继续保留。

### MappingAffectedObject 与 MappingReviewEvidence

`MappingAffectedObject` 不复制图对象，只索引候选 Commit 影响的对象：

- `candidate_commit_id`、`mapping_domain_id`；
- `object_type`：`TaskNode`、`DependencyEdge` 或 `FormalMappingRevision`；
- `logical_id`、`version_id`：TaskNode/DependencyEdge 使用；FormalMappingRevision 使用精确 `formal_revision_id`；
- `change_kind`：`added`、`modified`、`superseded`、`invalidated` 或 `restored`；
- `affected_fields`、`impact_summary`：字段级和调度影响摘要。

`MappingReviewEvidence` 保存审核材料的索引：

- `evidence_id`、`mapping_domain_id`；
- `owner_object_type`、`owner_object_id`、可选 `candidate_commit_id`；
- `evidence_type`：`diff`、`impact_preview`、`dry_run`、`approval` 或 `validation`；
- `summary`、`locator`、`generated_by`、`generated_at`；
- 可选 `content_checksum`，用于证明外部报告未被静默替换。

`locator` 必须是受控的证据定位或稳定引用，不得依赖本机绝对路径。证据索引不替代候选图内容。

### MappingFormalMappingRevision

表示一次成功建立的产品层正式版本记录，连接治理批准事实和 TerminusDB 正式快照。

- `formal_revision_id`、`mapping_domain_id`：必填且不可变。
- `terminus_store_id`、`formal_branch_id`、`formal_commit_hash`：精确正式图快照定位。
- `base_formal_revision_id`：可选父正式版本；首版正式版本为空。
- `source_proposal_id`、`source_merge_request_id`：产生该正式版本的候选来源。
- `approval_audit_event_id`：对应 Project Owner 明确批准的审计事件。
- `formalization_result_id`：成功建立该 Formal MappingRevision 的 SQLite 激活尝试记录。
- `published_by`、`published_at`：正式发布主体和时间。
- `snapshot_summary`：可选节点/边数量、摘要和校验信息，不复制图正文。

该记录与一次已确认成功的 FormalizationResult 双向关联，并指向已在激活前读回确认的不可变 TerminusDB Commit。Formal MappingRevision、SQLite 当前指针和 `succeeded` 结果必须在同一 SQLite 本地激活单元中持久化。

### MappingFormalizationResult

记录一次 Merge Request Buffer 的正式化操作及其有序尝试，不把 `approved` 直接等同于 `merged`。跨存储语义见 [`Research Mapping 跨存储正式化一致性与失败恢复设计`](./2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md)。

- `result_id`、`mapping_domain_id`、`merge_request_id`：必填；每次尝试有独立 `result_id`。
- `formalization_operation_id`：一次完整正式化操作的稳定身份；同一 Merge Request、方案、锁定候选 head、基准正式版本和批准事件的重试沿用同一值。
- `selected_solution_id`、`approval_audit_event_id`：所选完整方案和 Project Owner 批准事件。
- `result_status`：使用 `requested`、`in_progress`、`graph_ready`、`reconciliation_required`、`succeeded`、`failed`，语义和允许转换见跨存储正式化规格。
- `attempt_number`、`started_at`、`completed_at`：同一正式化操作下的尝试序号和时间。
- `formal_revision_id`、`formal_commit_hash`：仅在 SQLite 激活单元提交并将本次尝试标为 `succeeded` 后关联；其前置条件是 TerminusDB 精确 Commit 已读回确认。
- `error_code`、`error_summary`、`recovery_reference`：失败原因摘要和后续重试/对账/补偿记录引用。
- `candidate_head_commit_hash`、`base_formal_revision_id`：固定本次操作输入，用于幂等校验和防止候选过期后静默重放。

同一正式化操作通过唯一 `formalization_operation_id` 关联多次有序尝试，每个尝试独立记录 `result_id` 和 `attempt_number`；一次 Merge Request Buffer 至多有一个最终成功的操作结果，重试不得创建第二个逻辑 Formal MappingRevision。发生结果未知或两侧无法证明一致时，必须保留 `reconciliation_required` 记录，不得用普通 `failed` 隐藏部分完成。

### MappingAuditEvent

追加式记录提交、预审、审核、候选写入、锁定、正式化、失败、重试、通知和更正。

- `event_id`、`mapping_domain_id`、`occurred_at`；
- `actor_id`、`actor_type`、`operation`；
- `target_object_type`、`target_object_id`、可选 `target_version_id`；
- `previous_state`、`next_state`、`result`、`reason`；
- 可选 `submission_id`、`execution_record_id`、`proposal_id`、`candidate_commit_id`、`merge_request_id`、`solution_id`、`formal_revision_id`、`formalization_result_id`；
- 可选 `base_formal_revision_id`、`candidate_head_commit_hash`、`formalization_operation_id`、`evidence_id`。

AuditEvent 不能删除或原地改写；更正必须追加新事件并引用被更正事件。

### MappingNotification

记录提交者、审核者和 Project Owner 的通知意图及投递结果，不规定消息队列或传输实现。

- `notification_id`、`mapping_domain_id`；
- `recipient_id`、`notification_type`；
- `target_object_type`、`target_object_id`；
- `created_at`、`delivery_status`（例如 `pending`、`sent`、`failed`）；
- 可选 `delivered_at`、`failure_information`、`external_delivery_reference`。

通知失败不改变 Proposal、候选或正式版本事实；重发应产生可追踪的新投递记录或追加事件。

## 状态归属与关系约束

| 对象 | 状态/类型字段 | 权威语义 |
| --- | --- | --- |
| MappingBufferSubmission | `acceptance_status` | 提交接收、TaskNode Owner 接纳和 Central Agent 预审进度 |
| MappingProposal | `status` | 候选 Proposal 生命周期；不表示图内容是否已正式化 |
| MappingMergeRequestBuffer | `status` | 候选头锁定、PO 审核和正式化请求状态 |
| MappingCandidateSolution | `status`、`candidate_type` | 方案选择状态与 direct/blended 类型分离 |
| MappingSourceCommitDisposition | `final_disposition` | 来源候选在成功正式化后的最终处理结果 |
| MappingFormalizationResult | `result_status`、`formalization_operation_id` | 跨存储正式化尝试及其幂等身份；SQLite 激活单元写入 `succeeded` 才表示产品版本已激活，查询仍须校验当前指针与精确 TerminusDB Commit 匹配 |
| MappingNotification | `delivery_status` | 通知投递状态 |

必须满足：

1. 只有 `accepted` 的 Submission 才能关联 Proposal；一个 Submission 至多属于一个 Proposal。
2. 每个 CandidateCommit 只属于一个 Proposal，内容和 hash 不可变；候选分支在 MR 锁定后不得继续写入审阅范围。
3. Proposal、MR、CandidateSolution 的基准 Formal MappingRevision 必须一致；正式分支前进后，相关 Proposal/MR 必须进入 `stale` 或等价阻断状态，不能静默重放旧 candidate head。
4. 一个 MR 至多有一个 `selected` CandidateSolution 和一个最终成功 FormalizationResult；同一正式化操作可以有多个有序尝试，失败、对账、未选中和冲突记录保留。
5. 一个 `MappingFormalMappingRevision` 必须关联一个批准 AuditEvent、一个完整来源方案和一个精确正式 Commit；只能在 TerminusDB 精确 Commit 先读回确认后，通过 SQLite 激活单元同时创建/激活 Formal MappingRevision 和 `succeeded` 结果；正式版本身份和 Commit hash 不可复用。
6. `current_formal_revision_id` 在每个 `mapping_domain_id` 内至多有一个当前值；新 Formal MappingRevision 与当前指针必须在 SQLite 的同一业务激活单元内建立并切换，且只能从仍匹配的 `base_formal_revision_id` 前进；旧版本不删除，查询只读取双侧精确匹配的当前指针。
7. `MappingAffectedObject` 的对象引用必须包含稳定逻辑 ID 和版本 ID；同一 CandidateCommit 对同一对象版本至多有一条同类变更摘要。
8. Research Mapping 与 LLM-Wiki 不建立强外键。跨域 ID、来源任务和资源版本只带领域标识解释，目标不存在或版本不匹配时由对应领域校验器报告。

## 推荐索引语义

以下是领域查询需要的逻辑索引，不是 SQLite DDL：

- `(mapping_domain_id, proposal_id, status)`：查询候选治理状态；
- `(mapping_domain_id, base_formal_revision_id)`：发现过期候选和基准分叉；
- `(terminus_store_id, commit_hash)`：精确定位 CandidateCommit/正式 Commit；
- `(mapping_domain_id, merge_request_id, candidate_head_commit_hash)`：锁定审核头和幂等检查；
- `(candidate_commit_id, object_type, logical_id, version_id)`：按对象重建 Diff/影响范围；
- `(mapping_domain_id, formal_revision_id)`：查询正式版本链和当前正式指针；
- `(mapping_domain_id, target_object_type, target_object_id, occurred_at)`：重建审计时间线。

这些索引服务于可追溯查询，不能改变状态机或把索引命中当成业务批准。

## 场景一致性检查

1. **首次提交**：Submission 记录初始基准、ChangeSet 和目标对象；TaskNode Owner 接纳后进入 Proposal，CandidateCommit 记录精确 branch/hash；未形成 Formal MappingRevision 前，正式查询不读候选。
2. **修改和影响预览**：新节点/边版本写入 candidate branch；AffectedObject 和 ReviewEvidence 记录字段 Diff、依赖影响和调度变化；MR 锁定 candidate head 后所有审阅材料只读。
3. **Project Owner 驳回**：AuditEvent 记录批准或驳回主体、原因和基准；Proposal/MR 进入驳回状态，候选和证据保留，正式指针不变。
4. **正式化失败或部分完成**：保留 `approved` 审批事件、FormalizationResult 尝试、错误摘要和后续引用；没有成功双侧确认前，Formal Query 继续读取原正式版本。产生未激活图 Commit 或结果未知时使用 `graph_ready` / `reconciliation_required`，沿用同一 `formalization_operation_id` 对账或重试，不创建重复 Formal MappingRevision。通知失败只影响 Notification 投递状态，不改变已成功的正式版本。
5. **未来 blended 方案**：新建自己的 CandidateCommit 和 CandidateSolution，记录每个来源 Commit 的纳入、部分纳入或放弃范围；不能改写原来源分支。首版不执行该路径，但字段不会阻碍后续扩展。
6. **正式版本前进**：旧 Proposal/MR 的 `base_formal_revision_id` 保持不变；校验发现基准过期后进入 `stale` 或阻塞状态，必须从最新正式版本重建候选，不直接移动旧 candidate head。

## 排除范围

本设计不定义 SQLite DDL、ORM、API、消息队列、TerminusDB 事务实现、具体锁实现或通知传输协议。跨存储正式化的业务状态、提交确认、失败可见性、幂等重试、补偿和查询权威见 [`Research Mapping 跨存储正式化一致性与失败恢复设计`](./2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md)。本设计只负责让所有输入、候选、审核、Commit、Formal MappingRevision 和审计事实具备稳定字段与可追溯关系。
