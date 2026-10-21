# Research Mapping 与 LLM-Wiki 正式实施收敛设计

- 日期：2026-10-20
- 范围：`ai4-6ljq`、`ai4-mqtq`、`ai4-6s53`、`ai4-z0lb`、`ai4-1qyc`、`ai4-orpg`、`ai4-vczt`、`ai4-91tk`、`ai4-txhf`、`ai4-jdjx`
- 状态：方案 A 已确认，作为实现工单的共同实施契约

## 目标

把 Research Mapping 和 LLM-Wiki 的活跃实现工单收敛为可以直接拆分给工程师执行的实施契约。实施必须保留两个领域独立的存储、治理、审计和查询边界，同时让每张纵向工单拥有明确的代码位置、内部接口、数据职责、环境配置和验证证据。

## 架构选择

采用两个独立 Python 子项目：

- `sci-weave/research-mapping/`
- `sci-weave/llm-wiki/`

两个子项目分别维护自己的 `pyproject.toml`、`uv.lock`、`.env.example`、`src/main.py`、业务包和 `tests/`，声明 `requires-python = ">=3.11"`（与现有 SciWeave Python 子项目一致）。不把两个领域放入现有 `sci-weave/task-agent` 项目组，也不建立跨领域共享 Python 包。Mapping 和 Wiki 之间只使用带领域语义的稳定 ID/版本 ID 弱引用；不共享 SQLite 文件、TerminusDB Store、MCP、审计表或跨存储事务。

本轮实现以领域应用服务和存储适配器为主，不新增 MCP 或 Web API。`src/main.py` 负责读取环境配置并组装服务依赖，后续 Gateway/MCP 工单通过稳定的应用服务接口接入。这样可以先验证正式查询、候选治理和跨存储恢复，再决定外部传输层。

## 依赖策略

首版只使用 Python 标准库和仓库已固定的 TerminusDB 本地验证服务：

- SQLite 使用标准库 `sqlite3`；
- JSON、哈希、UUID、时间和 HTTP 适配使用标准库；
- TerminusDB 使用本地 HTTP 适配器，外部请求封装在可替换的 `TerminusStore` 接口后；
- 单元测试使用内存/临时 SQLite 和 Fake TerminusStore；
- 集成测试通过环境变量连接仓库已有的 TerminusDB 12.0.8 验证服务；
- 不新增 SDK、ORM、Web 框架、迁移工具或测试框架。

如果实现确实需要第三方包，必须先创建依赖工单，记录来源、版本约束、用途、许可证/限制、安装命令和验证命令，再修改对应 `pyproject.toml` 和锁文件。

## 共同实现约定

### 标识、时间和幂等

- 业务 ID 使用字符串 UUID，由服务生成或验证，标题、分支名和展示名称不能作为关联键。
- 持久化时间统一为 UTC RFC 3339 文本，原始创建时间不覆盖。
- 需要内容身份的请求先用标准库 `json.dumps(..., sort_keys=True, separators=(",", ":"))` 生成规范 JSON，再计算 SHA-256。
- 候选提交的幂等键至少绑定领域 ID、提交 ID、正式基准、规范内容摘要和提交者；同一输入重试返回原结果，不同内容复用同一提交身份时返回幂等键冲突。
- 正式化操作使用规格中定义的稳定 `formalization_operation_id`；重试只增加 `attempt_number`，不生成第二个正式版本。

### SQLite 边界

SQLite 只保存治理事实、状态、审计索引和 TerminusDB 精确定位，不保存候选或正式图/文档正文。每个子项目使用自己的数据库路径，并在连接后启用外键约束。正式激活使用本地事务和条件更新：条件不满足时整个激活单元回滚，不能覆盖其他操作已经建立的当前指针。

### TerminusDB 边界

TerminusDB 只保存该领域的不可变内容快照和精确 Commit。应用层只允许通过 `TerminusStore` 访问精确 store/database/branch/commit；共享读取契约 `read_exact_snapshot(...)` 返回 `confirmed`、`missing` 或 `unavailable`，确认结果必须带精确 Commit 身份和内容 SHA-256。Mapping/Wiki 候选通过 `create_candidate_snapshot(...)` 写入隔离分支，正式化通过 `create_formal_snapshot(...)` 写入精确正式快照；写操作区分明确失败和 `result_unknown`，未知结果按原操作身份读回。Wiki 另提供 `read_resource_version(location, resource_version_id)`，`location` 是写入时固定到治理记录的精确 store/database/branch/commit 四元组；读取只在该 Commit 上按版本 ID 选取文档，精确返回版本和所属资源元数据，版本 ID 本身不解析位置。正式查询禁止调用“当前最新 Commit”或候选分支回退；所有 HTTP 实现细节留在可替换适配器内。

### 失败关闭

正式查询遇到无正式版本、SQLite 指针与正式记录不一致、精确 Commit 不可读或两侧内容不匹配时，返回结构化不可用结果；不返回候选、不静默回退、不选择最新版本。通知失败独立记录，不改变已经成功的正式化结果。

## Research Mapping 实施结构

`ai4-mqtq` 创建并固定以下最小结构，后续 Mapping 工单在此基础上增量实现：

```text
sci-weave/research-mapping/
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── src/
│   ├── main.py
│   └── research_mapping/
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── canonical.py
│       ├── domain.py
│       ├── schema.sql
│       ├── sqlite_store.py
│       ├── terminus_store.py
│       ├── formal_query.py
│       ├── candidate_submission.py
│       ├── review.py
│       └── formalization.py
└── tests/
    ├── test_formal_query.py
    ├── test_candidate_submission.py
    ├── test_review.py
    ├── test_formalization.py
    └── test_terminus_integration.py
```

### Mapping 的最小内部契约

- `FormalQueryService.get_current(mapping_domain_id)`：读取 SQLite 当前正式指针、匹配的 `FormalMappingRevision` 和 `succeeded` FormalizationResult，再按精确 Commit 读取图快照；结构化结果区分 `available`、`no_formal_revision`、`inconsistent` 和 `unavailable` 并带稳定原因码，只有 `available` 可以包含图正文。
- `MappingCandidateService.submit(change_set, idempotency_key)`：校验 TaskNode/DependencyEdge 端点、版本、状态、无自环和 blocking 子图无环；在候选 branch 创建不可变 Commit，并在 SQLite 写入 Submission、Proposal、CandidateCommit 和 AuditEvent。候选写入或治理记录结果未知时返回 `result_unknown` 并按同一幂等身份读回，不得盲目创建重复候选。
- `MappingReviewService.preview(proposal_id, base_formal_revision_id, candidate_head)`：生成字段级差异、受影响对象和路线影响摘要；基准或 candidate head 变化时预览失效。
- `MappingFormalizationService.formalize(merge_request_id, operation_id)`：执行资格确认、精确图 Commit 写入/读回、SQLite 条件激活和对账恢复；使用 `graph_ready` 与 `reconciliation_required` 等 Mapping 规格状态。

Mapping SQLite 至少覆盖 Submission、Proposal、CandidateCommit、MergeRequestBuffer、CandidateSolution、AffectedObject、ReviewEvidence、FormalMappingRevision、FormalizationResult、AuditEvent 和 Notification 的治理记录。TaskNode/DependencyEdge 正文始终由 TerminusDB 持有。

### Mapping 验证证据

每张 Mapping 实现票都必须提供标准库 `unittest` 测试、临时 SQLite 数据和 Fake TerminusStore 测试；需要真实存储行为时使用仓库已有 TerminusDB 服务，并从本地 `.env` 读取地址、数据库、Store 和令牌。每个 README 至少声明 `uv sync --locked`、`uv run --env-file .env python -m unittest discover -s tests -v`，以及显式执行 `test_terminus_integration.py` 的命令；集成测试缺少服务配置时不得把跳过记作已验证。测试必须覆盖成功路径和规格要求的失败/未知结果，不依赖固定部署端口。

## LLM-Wiki 实施结构

`ai4-vczt` 创建并固定以下最小结构，后续 Wiki 工单在此基础上增量实现：

```text
sci-weave/llm-wiki/
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── src/
│   ├── main.py
│   └── llm_wiki/
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── canonical.py
│       ├── domain.py
│       ├── schema.sql
│       ├── sqlite_store.py
│       ├── terminus_store.py
│       ├── resource_review.py
│       ├── formal_query.py
│       ├── candidate_submission.py
│       ├── review.py
│       └── formalization.py
└── tests/
    ├── test_resource_review.py
    ├── test_formal_query.py
    ├── test_candidate_submission.py
    ├── test_review.py
    ├── test_formalization.py
    └── test_terminus_integration.py
```

### Wiki 的最小内部契约

- `ResourceReviewService.record_decision(resource_version_id, actor, decision, reason, evidence, scope, authority_context)`：只接受可信组合边界提供且可验证的 actor/authority context；审核记录追加保存。缺少授权时保持 `pending` 并记录审计尝试，不伪造 `approved` 或 `rejected` 资格决定；`get_current_qualification(resource_version_id, requested_scope)` 按追加序列和适用范围计算当前资格。不得引入未确认的身份服务或以自由文本/自报角色代替授权验证。
- `WikiFormalQueryService.get_current(wiki_domain_id)`：读取 SQLite 当前正式指针、成功 `FormalizationResult` 和精确 WikiRevision Commit；返回 `available`、`no_formal_revision`、`inconsistent` 或 `unavailable` 并带稳定原因码，只有 `available` 可返回正文。Resource Reference 按精确 WikiRevision/ResourceVersion ID 解析，资格撤回只显示当前状态，不改写目标。
- `WikiCandidateService.submit(document_change, idempotency_key)`：以完整文档正文和完整 Resource Reference 集合作为原子接纳单元，验证引用目标和领域边界，生成隔离 Proposal/candidate head，并显示资源资格状态；不同内容复用同一幂等身份时返回 `idempotency_conflict`，存储写入结果未知时返回 `result_unknown` 并按原身份读回，不能盲目创建重复候选。
- `WikiReviewService.preview/decide(...)`：绑定固定 candidate head 和 base Formal WikiRevision，记录文档/引用审核、资源资格检查、Owner 选择/驳回和审计事件；任何基准或候选变化都会使旧预览失效。
- `WikiFormalizationService.formalize(merge_request_id, operation_id)`：在 Project Owner 批准后再次检查每个 ResourceVersion 的当前有效且范围适配的批准，写入并读回 TerminusDB 精确 Commit，再以 SQLite 本地激活单元完成正式化；使用 Wiki 规格的 `store_ready`、`reconciliation_required` 和 `succeeded` 状态。

Wiki SQLite 至少覆盖 ResourceVersionReview、WikiBufferSubmission、WikiProposal、WikiCandidateCommit、WikiMergeRequestBuffer、WikiCandidateSolution、AffectedObject、ReviewEvidence、FormalWikiRevision、FormalizationResult、AuditEvent 和 Notification。WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 与 Resource Reference 正文和内容快照由 Wiki TerminusDB 持有；SQLite 不复制正文。

### Wiki 验证证据

资源审核必须测试授权、越权、待审、批准、拒绝、撤回、重新批准、范围限制、未知证据和追加审计。正式查询必须测试精确引用、资格提示、候选隔离和两侧不一致。候选和正式化必须测试完整引用接纳、基准过期、Owner 决策、TerminusDB/SQLite 失败、未知结果恢复和通知失败。每个 README 声明 `uv sync --locked`、`uv run --env-file .env python -m unittest discover -s tests -v` 和显式执行 `test_terminus_integration.py` 的命令；集成测试缺少服务配置时不得把跳过记作已验证。SQLite 使用临时数据库，服务地址从 `.env` 读取，不写死部署端口。

## 环境配置

两个子项目的 `.env.example` 只提交变量名和非敏感示例，不保存真实凭据、服务地址或固定部署端口。Mapping 声明：

- `SCIWEAVE_MAPPING_SQLITE_PATH`
- `SCIWEAVE_MAPPING_DOMAIN_ID`
- `SCIWEAVE_MAPPING_TERMINUSDB_URL`
- `SCIWEAVE_MAPPING_TERMINUSDB_DATABASE`
- `SCIWEAVE_MAPPING_TERMINUSDB_STORE`
- `SCIWEAVE_MAPPING_TERMINUSDB_TOKEN`

Wiki 声明：

- `SCIWEAVE_WIKI_SQLITE_PATH`
- `SCIWEAVE_WIKI_DOMAIN_ID`
- `SCIWEAVE_WIKI_TERMINUSDB_URL`
- `SCIWEAVE_WIKI_TERMINUSDB_DATABASE`
- `SCIWEAVE_WIKI_TERMINUSDB_STORE`
- `SCIWEAVE_WIKI_TERMINUSDB_TOKEN`

源代码仅读取由进程环境提供的值，不自行解析 `.env`；本地运行通过 `uv run --env-file .env ...` 注入配置。测试使用内存/临时 SQLite 和 Fake TerminusStore；Termin​​usDB 集成测试在仓库本地验证服务运行时显式执行，并从 `.env` 读取 URL、数据库、Store 和令牌，不依赖固定部署端口。

## 工单执行顺序

Mapping 顺序保持为：`ai4-mqtq` → `ai4-6s53` → `ai4-z0lb` → `ai4-1qyc`。其中 `ai4-mqtq` 负责子项目骨架和可复用存储 seam，避免后续工单重复决定部署位置和适配器接口。

Wiki 顺序保持为：`ai4-vczt` → `ai4-91tk` → `ai4-txhf` → `ai4-jdjx`。其中 `ai4-vczt` 负责子项目骨架和资源资格持久化/查询 seam，后续工单复用该边界。

两个链条可以并行推进，但不得合并为一个跨域工单，也不得添加 Mapping/Wiki 之间的阻塞依赖。每张工单完成后必须回写实际文件、运行命令、测试结果、锁文件和任何依赖变化；关闭前必须通过 `ticket_index.py check` 和 `fer dep cycle`。

## 完成定义

本轮工单收敛完成不等于代码完成。工单达到“可正式实施”必须同时满足：

1. 有明确的独立子项目路径和启动入口；
2. 有明确的 SQLite/TerminusDB 职责与不变量；
3. 有稳定内部服务接口、状态/错误结果和幂等规则；
4. 有环境变量、锁文件、测试替身和本地 TerminusDB 验证方式；
5. 有成功、失败、结果未知、对账和通知失败的独立验收证据；
6. 没有未经确认的 SDK、数据库、队列或部署依赖；
7. 子票依赖能由 `fer` 查询且无循环。

本设计不关闭任何实现工单，不改变已关闭的领域决策，也不把 MCP、消息协作、Agent 套件或 Web 前端纳入两个模块的本轮实现范围。
