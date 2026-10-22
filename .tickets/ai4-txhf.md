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

## Implementation Contract

- **代码位置与接口：** 在 `sci-weave/llm-wiki/src/llm_wiki/candidate_submission.py` 实现 `WikiCandidateService.submit(document_change, idempotency_key)`；复用 `WikiFormalQueryService`、ResourceReviewService、SQLiteStore 与 TerminusStore，不另建服务。
- **接纳原子单元：** 每个 BufferSubmission 必须以一份 WikiDocument 变更的完整正文、结构化字段和完整 Resource Reference 集合为不可拆分输入；多个文档可由一个 Proposal 聚合，但每份内容仍按其完整引用集合验收。候选引用必须绑定精确 ResourceVersion ID 或符合规格的精确 WikiRevision ID，拒绝不存在、跨领域和指向其他 Proposal 候选的非法目标。
- **隔离与幂等：** 依据精确 FormalWikiRevision 基准写入 TerminusDB 隔离 candidate branch/head；扩展 `TerminusStore.create_candidate_snapshot(domain_id, base_commit_ref, canonical_snapshot, idempotency_key)`，仅确认时返回精确 commit ref。内容不可变，SQLite 事务写入 WikiBufferSubmission、WikiProposal、WikiCandidateCommit 和 AuditEvent。规范 JSON/SHA-256 与稳定业务 ID 绑定提交身份、提交者、领域、基准和内容；重复同一输入返回原结果，复用身份提交不同内容返回 `idempotency_conflict`，绝不覆盖其他候选。
- **资源资格门槛：** 待审/拒绝/撤回的精确资源引用允许留在隔离候选并显示其真实状态，但不能呈现为已批准，也不能创建可供 Project Owner Formal Publication Review 的有效请求。此处不代替资源资格审核或文档/引用审核。
- **失败和验证：** 明确区分输入拒绝、基准冲突、存储明确失败与结果未知；未知结果保留精确候选证据并要求按原幂等身份读回/对账，不能谎报成功或产生重复候选。新增 `tests/test_candidate_submission.py` 覆盖完整引用接纳、非法目标、基准过期、幂等重复/冲突、资格提示/门槛、存储失败/未知及候选隔离；按 Wiki 地图命令运行，不加测试依赖。

## Acceptance Criteria

- [ ] 以完整文档正文、结构化属性和完整 Resource Reference 集合作为单元创建 BufferSubmission；正文与引用关系不得部分接纳。
- [ ] 候选每条引用精确绑定 ResourceVersion/WikiRevision ID；缺失目标、跨领域目标或不允许的候选目标被拒绝，不自动解析“最新版本”。
- [ ] 待审/被拒/已撤回资源允许保留在隔离候选并显示资格；不能呈现为批准或进入可批准的 Project Owner 正式审核/正式化。
- [ ] 接纳后生成独立 Proposal/candidate branch 与不可变候选版本，并记录提交者、提交身份、正式基准、精确 Commit 及审计关联。
- [ ] 同一幂等身份及内容返回原结果；不同内容冲突且不覆盖其他候选。存储未知结果可读回对账，不盲目创建重复 Commit/Proposal。
- [ ] `tests/test_candidate_submission.py` 覆盖成功、完整引用、非法目标、基准过期、幂等、资格门槛及存储失败/未知；实际运行命令和验证结果回写本票。

## Notes

- 2026-10-22：当前身份核对通过：本票 assignee 为 `hanjiang`，当前分支为 `feature/hanjiang`，`git config user.name` 为 `hanjiang`。
- 2026-10-22：本轮复验 `uv sync --locked` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 82 项，全部通过；`uv run --locked python -m compileall -q src tests` 成功。真实 TerminusDB 12.0.8 服务已启动，使用当前 PowerShell 进程变量指定本地地址 `http://127.0.0.1:6363`、本地临时验证数据库前缀 `sciweave_wiki_it` 和 Basic 凭据；命令 `uv run --locked python -m unittest discover -s tests -p 'test_*integration.py' -v` 共 12 项全部通过，覆盖真实 ResourceReviewService 精确资源资格查询、候选隔离分支及精确 Commit 写读回、Formal Wiki 快照、Owner 正式化、正式查询，以及 Owner 批准后资源撤回阻止激活。临时数据库由用例创建并清理，凭据未写入文件或仓库。
