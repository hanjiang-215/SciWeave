---
id: ai4-xrxw
status: closed
deps: [ai4-ay0e, ai4-r3so]
links: [ai4-u3rs, ai4-dy2x, ai4-r3so, ai4-m0vt]
created: 2026-10-17T15:21:25Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, proposal, audit, product, ai4science]
---
# 首版 Mapping Proposal 生命周期与审计证据模型

明确 Research Mapping 首版 Proposal 的生命周期、Formal Mapping 查询与正式调度门槛、候选 Diff/影响预览和 AuditEvent 最小关联。只确定产品与领域治理规则，不复制 TerminusDB 的存储实现，也不扩展 LLM-Wiki。

## Design

首版采用单领域、单候选演示路径，同时保留未来并行候选所需的版本锁定语义：

```text
MCP Submission
→ Mapping Buffer
→ TaskNode Owner 接纳审核
→ Central Agent 预审
→ Proposal candidate branch
→ candidate Commit
→ candidate head lock
→ Merge Request Buffer
→ diff / impact preview
→ Project Owner Formal Publication Review
→ Formal MappingRevision
```

- Buffer 接收结构化提交，但不改变 Formal Mapping。
- TaskNode Owner 负责确认提交属于该任务、完成条件和证据边界；Central Agent 负责格式、引用、依赖、权限、基准版本和影响范围预审。
- Candidate branch 只承载候选内容，candidate Commit 只表示存储版本，不代表已经批准。
- 创建 Merge Request Buffer 时固定 `candidate_head`。被锁定的 head、祖先 Commit 和 Diff 进入只读审查范围，不能继续追加写入。
- Project Owner 只能批准完整候选或驳回完整候选。正式化后生成新的 Formal MappingRevision；TerminusDB rebase 或其他存储操作不能单独代表审批。
- 首版不实现并行候选、blended candidate 或跨域 Proposal；这些能力保留为后续扩展，不改变本票据的首版边界。

## 状态和转换

### Mapping Buffer Submission

```text
received → owner_review → accepted → central_pre_review → candidate_created
                         └→ rejected
```

- `received`：平台已接收并记录提交。
- `owner_review`：等待 TaskNode Owner 检查归属、任务完成条件和证据引用。
- `accepted`：允许进入 Central Agent 预审；不表示正式批准。
- `central_pre_review`：检查结构、引用、权限、依赖、基准版本和影响范围。
- `candidate_created`：通过预审后写入 Proposal candidate branch。
- `rejected`：保留拒绝原因；重新提交必须生成新的 Submission，不修改原记录。

### Proposal

```text
draft → candidate → mr_ready → merged
                    ├→ rejected
                    ├→ stale
                    ├→ conflict
                    └→ abandoned
```

- `draft`：已接纳但候选内容仍在准备。
- `candidate`：已形成候选版本，可继续产生候选 Commit，直到提交正式化请求。
- `mr_ready`：Merge Request Buffer 已创建，candidate head 已锁定。
- `merged`：Project Owner 批准并生成 Formal MappingRevision。
- `rejected`：Project Owner 明确不批准，候选和意见保留为只读审计对象。
- `stale`：基准 Formal MappingRevision 已经前进，不能直接正式化，必须基于最新正式版本重新生成候选。
- `conflict`：Diff 或 dry-run 发现同一节点、边、依赖或基准版本存在冲突，必须生成新的候选解决版本。
- `abandoned`：提交者或 Project Owner 明确放弃，不能继续追加写入。

Proposal 状态不可通过覆盖历史记录回退。被拒绝、过期、冲突或废弃的 Proposal 如需修订，必须从最新 Formal MappingRevision 创建新的 Submission 和 Proposal。

### Merge Request Buffer

Merge Request Buffer 使用 `draft`、`submitted`、`conflict`、`stale`、`approved`、`rejected`、`merged` 状态。它只保存治理请求和候选引用，不重复保存 Mapping 正文。一个 Merge Request Buffer 只允许产生一个 Formal MappingRevision。

## 并发、锁定和不可变性

- 每个 Proposal 记录 `base_formal_revision_id`、`candidate_branch_id`、当前 `candidate_head` 和候选 Commit 列表。
- Candidate Commit 内容不可变；Candidate branch 在未创建 Merge Request Buffer 前可以追加候选 Commit。
- 一旦锁定 candidate head，相关候选、祖先 Commit、Diff 和影响预览只能读取；需要修改时创建新的候选版本或新的 Proposal。
- 如果正式分支在锁定后前进，正式化检查必须标记 `stale`，不能直接 rebase 后自动发布。
- 如果候选与正式版本或其他候选修改同一逻辑对象，必须通过领域 Diff/merge dry-run 生成 `conflict`；解决结果必须是新的候选 Commit，不能修改原候选。
- TerminusDB 的 branch 状态、Commit 和 rebase 不能承载 Proposal 状态、审批结果或只读归档事实，这些事实由平台结构化治理记录保存。

## Diff 与影响预览

候选 Diff 至少说明：

- 新增、修改、废弃或恢复的 TaskNode 和 DependencyEdge；
- 节点目标、完成条件、输入输出和责任主体的变化；
- 依赖可达性、阻塞关系、条件分支和路线激活条件的变化；
- 哪些节点从不可调度变为可调度，或从可调度变为阻塞；
- 受影响的 Resource Reference、Execution Record 和待处理人工判断点；
- 候选基准、candidate Commit、Formal MappingRevision 和影响分析生成时间。

Diff 是负责人审核的解释材料，不是正式批准本身。影响预览中出现的候选内容必须明确标记为 `candidate`，不能被正式查询或正式调度读取。

## 查询和正式调度边界

- 普通查询和 Formal Query 只读取当前 Formal MappingRevision 中有效的正式节点和边。
- Proposal Preview 必须带有 `proposal_id`，只读取该 Proposal 的候选内容，并明确显示基准版本和候选状态。
- 正式调度只允许读取当前 Formal MappingRevision；节点和所有相关边必须属于该版本，满足前置阻塞条件，输入和正式证据引用可用，且没有未完成的人工判断点。
- Central Agent 可以执行已批准候选的存储推进，但必须先验证 Project Owner 的批准事件、候选 head、基准版本、冲突检查和影响预览结果。
- 未批准、被拒绝、未选中、过期、冲突或废弃候选不得进入正式查询、正式调度或正式科研结果发布。

## 审核责任边界

1. TaskNode Owner 进行第一阶段接纳审核，检查提交归属、任务完成条件、结果摘要和证据引用。
2. Central Agent 进行结构和治理预审，检查格式、引用、权限、依赖、版本基准、冲突和影响范围。
3. Project Owner 进行 Formal Publication Review，明确批准或驳回完整候选，并对正式科研事实承担最终责任。
4. 任何角色都不能通过直接写入 TerminusDB formal branch 绕过上述审核；未经 Project Owner 明确批准，不得生成 Formal MappingRevision。

## AuditEvent 最小关联

每个 AuditEvent 至少记录：

- `event_id`、`timestamp`、`actor_id`、`actor_type`；
- `operation`、`from_state`、`to_state`、`result` 和 `reason`；
- `target_id`、`target_version_id`；
- `submission_id`、`execution_record_id`、`proposal_id`；
- `base_formal_revision_id`、`candidate_branch_id`、`candidate_commit_id`、`candidate_head`（适用时）；
- `formal_revision_id`（正式化后）；
- 关联的 Diff/影响预览标识和人工审核意见（适用时）。

AuditEvent 追加写入，不通过覆盖或删除历史事件实现回滚。审计查询应能重建“谁在什么正式基准上提交了什么、候选如何变化、谁审核、谁批准、最终形成哪个 Formal MappingRevision”。

## Acceptance Criteria

- [x] 形成 Proposal、Mapping Buffer Submission、candidate head 和 Merge Request Buffer 的状态清单、转换规则和不可逆边界。
- [x] 明确 MCP Submission、candidate head、Diff、影响预览、Merge Request Buffer 与 Formal MappingRevision 的最小关系。
- [x] 明确普通查询、候选预览、Formal Query 和正式调度的边界。
- [x] 明确 TaskNode Owner 接纳审核、Central Agent 预审和 Project Owner 正式发布审核的责任边界。
- [x] 明确 AuditEvent 的最小字段和关联对象。
- [x] 明确被拒绝、过期、冲突和废弃候选的保留与只读审计规则。
- [x] 不引入具体 TerminusDB 存储实现，也不扩展 LLM-Wiki。

## Answer

Research Mapping 首版采用单候选、两阶段人工审核和平台治理版本的 Proposal 闭环。执行失败本身不创建 Proposal，只有改变正式研究路线的结构化 ChangeSet 才进入本生命周期；正式查询和正式调度始终只面向当前 Formal MappingRevision。

## Notes

**2026-10-18T08:28:55Z**

已完成首版 Mapping Proposal 生命周期：明确 Buffer、TaskNode Owner 接纳、Central Agent 预审、candidate head 锁定、Diff/影响预览、Formal Query、正式调度、Project Owner 正式审核和 AuditEvent 关联；首版保持单候选、不扩展 LLM-Wiki。验收标准全部满足。
