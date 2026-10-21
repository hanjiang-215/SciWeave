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

## Implementation Contract

- **代码位置与接口：** 在 `sci-weave/llm-wiki/src/llm_wiki/review.py` 实现 `WikiReviewService.preview(...)`/`decide(...)`，在 `formalization.py` 实现 `WikiFormalizationService.formalize(merge_request_id, operation_id)` 与恢复入口；复用前置服务和稳定内部 DTO，不实现外部网络 API。
- **审核固定输入：** Preview/MergeRequestBuffer 使用 `TerminusStore.read_exact_snapshot(...)` 读取并固定精确 candidate head、base FormalWikiRevision、完整方案和证据。候选头/正式基准变化使 preview 失效；审核决定记录 Project Owner 身份、时间、决定、理由、所选方案和 AuditEvent。资源资格审核、Wiki Submission 接纳/引用审阅及 Project Owner Formal Publication Review 是三个独立证据，不得互相代替。
- **正式化前置条件：** 正式化前、Project Owner Review 前和 SQLite 激活时，检查每个精确 ResourceVersion 仍有当前有效且范围适配的批准；Owner 必须对固定基准和完整方案另行批准。若资源批准在 Owner 批准后、SQLite 激活前撤回/更改，阻止激活；重新取得适用资源批准后必须重新进行 Owner 批准并创建新 `formalization_operation_id`。
- **跨存储状态与唯一生效点：** 使用 Wiki 规格状态 `requested`、`in_progress`、`store_ready`、`reconciliation_required`、`succeeded`、`failed`。先调用 `TerminusStore.create_formal_snapshot(locked_candidate_ref, operation_id)` 写入精确 commit，再调用 `read_exact_snapshot(...)` 读回核对；`store_ready` 仅表示 Commit 已确认，不表示正式。随后以单一 SQLite 事务条件检查基准未变化、资源批准仍有效，创建 FormalWikiRevision、切换当前指针、写 `succeeded` 结果（含精确 Commit 和每个 ResourceVersion 的批准决定 ID），并同步成功所需的 MR/Proposal 来源处置。事务提交是唯一生效点。
- **恢复与通知：** `formalization_operation_id` 绑定 MR、方案、head、base 和 Owner 批准事件；同一操作重试只递增 attempt_number，复用精确 Commit，不重复创建正式版本。结果未知进入 `reconciliation_required`，通过操作身份及双侧读回确认；证据不足时不激活、不报成功、不盲目重试。TerminusDB 已确认而 SQLite 激活失败时保持旧正式版；不要求物理回滚。通知在成功后发送，失败不撤销正式版，单独记录通知状态与审计。
- **验证：** 新增/完善 `tests/test_review.py`、`tests/test_formalization.py` 及真实 TerminusDB 集成用例，覆盖冲突/无冲突、Owner 驳回、资源批准撤回、基准过期、成功、TerminusDB 明确失败/未知、SQLite 激活回滚/未知、幂等恢复和通知失败；使用 Fake 适配器和临时 SQLite 测试。命令和环境继承 Wiki 地图；不添加依赖或固定部署端口。

## Acceptance Criteria

- [ ] 差异和冲突检查绑定精确 candidate head 与 base FormalWikiRevision；基准前进或 head 变化时旧预览不可直接批准。
- [ ] Merge Request Buffer、Owner 选择/驳回、理由、锁定输入和审计可追踪；候选内容和历史 Commit 不被改写。
- [ ] 资源资格检查、文档/引用审核和 Project Owner Formal Publication Review 分别保存证据；没有当前有效、范围适配的资源批准时不能发起 Owner 正式审核或正式化。
- [ ] 资源批准在 Owner 批准后、激活前发生变化时，SQLite 激活被条件阻断；重新取得资源批准后须重新获得 Owner 批准并创建新正式化操作身份。
- [ ] 新 FormalWikiRevision、条件指针切换、成功结果及成功所需来源处置在同一个 SQLite 激活事务中提交；此前普通查询仍返回旧版本。
- [ ] 状态采用规格规定的 `requested`、`in_progress`、`store_ready`、`reconciliation_required`、`succeeded`、`failed`；明确失败、未知结果及恢复不会混淆或跳过双侧确认。
- [ ] 同一操作幂等重试复用原身份与精确 Commit，不产生第二个正式版本；通知失败不回滚正式版，所有对账/修复/人工处置追加审计。
- [ ] `tests/test_review.py`、`tests/test_formalization.py` 和集成测试覆盖冲突、驳回、成功及跨存储失败恢复；记录测试命令、服务配置和结果。
