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

## Implementation Contract

- **代码位置与接口：** 在 `sci-weave/llm-wiki/src/llm_wiki/formal_query.py` 实现 `WikiFormalQueryService.get_current(wiki_domain_id)`，复用 `ai4-vczt` 提供的 SQLiteStore、TerminusStore 和 ResourceReviewService；不建立另一套存储或外部传输层。
- **查询资格与结果：** SQLite 当前正式指针、匹配的 FormalWikiRevision 和关联 `WikiFormalizationResult.result_status = succeeded` 共同决定唯一可读版本。返回 `available`、`no_formal_revision`、`inconsistent` 或 `unavailable` 之一，并提供稳定 `reason_code`；只有 `available` 返回正文和结构化引用。`requested`、`in_progress`、`store_ready`、`reconciliation_required`、`failed` 均不能提供新正式版本。
- **精确内容读取：** 调用 `TerminusStore.read_exact_snapshot(store_id, database, branch_id, commit_hash)` 按 FormalWikiRevision 记录的精确位置读取并核对身份和规范内容摘要，不使用 branch 最新 commit 或 candidate。Resource Reference 保持精确 WikiRevision/ResourceVersion ID；按精确 ResourceVersion ID 和请求范围读取当前资格与限制，资格未知时显式显示为 pending/unknown，绝不改指新版本。历史引用在目标不可用或资格已撤回时仍保留原目标及状态提示。
- **失败关闭：** 无正式版本返回 `no_formal_revision`；指针、正式记录、成功结果、commit 身份或内容不一致返回 `inconsistent`；精确 Commit 不可读或存储调用结果无法确认返回 `unavailable`/需对账原因。所有不可用结果都不含候选或新版本正文，不静默前进/回退。资源资格暂不可读不得被显示为批准。
- **验证：** 新增 `tests/test_formal_query.py`，以临时 SQLite/Fake TerminusStore/Fake ResourceReviewService 覆盖首次查询、成功版本、精确引用、历史/撤回资格提示、候选隔离、无正式版本、状态不合格、指针/Commit/摘要错配和存储故障；另在 `tests/test_terminus_integration.py` 增加仓库 TerminusDB 精确 commit 读回用例。命令、环境和依赖遵循 Wiki 地图及 `ai4-vczt` README。

## Acceptance Criteria

- [ ] 普通读取仅返回 SQLite 当前指针、FormalWikiRevision 和 `succeeded` 结果共同确认的精确正式版本、完整正文及结构化引用。
- [ ] 每条引用解析到原始精确 WikiRevision 或 ResourceVersion ID；目标失效、过期或资格被撤回时保留原 ID 并提示，不自动跳到最新版本。
- [ ] 资源资格按精确 ResourceVersion ID/范围呈现当前决定、限制或 pending/unknown；不能把未知显示为批准，也不能改写历史引用。
- [ ] 候选、待审、Owner 未批或正式化未完成内容不通过普通正式查询暴露；非 `available` 结果不含正文。
- [ ] 无正式版本、成功结果缺失、指针/存储不一致、精确版本不可读或结果未知均返回明确结果，不静默回退或前进。
- [ ] `tests/test_formal_query.py` 覆盖上述成功、隔离、资格提示及失败路径；真实 TerminusDB 集成证据与单测证据分别记录。
