---
id: ai4-vczt
status: closed
deps: [ai4-7xtf]
links: []
created: 2026-10-20T13:29:04Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, implementation]
---
# Wiki ResourceVersion 资格审核与撤回纵向实现

实现 LLM-Wiki 对精确 ResourceVersion 的独立资格审核记录，供候选准备、正式查询和正式化校验使用。资源资格审核不替代 Wiki Submission 接纳审核、Wiki 文档/引用审核或 Project Owner Formal Publication Review。

## Design

遵循 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)、[`LLM-Wiki 内容模型`](../docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md) 与 [`Wiki 候选治理记录模型`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md)。审核以不可变 `resource_version_id` 为目标，审核记录追加保存；每条决定可追溯 reviewer 身份、Resource Owner 或明确授权来源、结论、理由/证据、时间、使用范围和限制。仅有自由文本审计备注不能代替结构化资格决定。

只有 Resource Owner 或具备可追溯授权的审核人可以作出资源资格决定。审核需记录版本身份/内容快照识别能力、来源与生成信息、许可/署名限制、访问定位及 `handling_mode`；未知项必须显式记录。当前资格由该 ResourceVersion 最近一项有效审核决定及其适用范围确定；拒绝或撤回阻止新的正式化，后续批准可以恢复资格。对外部内容不能固定或无法取得哈希的有限批准，必须保留不可复现限制。

候选可以引用待审或被拒的精确 ResourceVersion，但必须显示其资格状态，且不得呈现为已批准。资格决定不得随 Wiki 文档审核而隐式产生；资源审核撤回不得改写既有正式 WikiRevision 或其精确引用。资格状态应能被其他 Wiki 实现切片按稳定版本 ID 查询；不建立与 Research Mapping 的强关系，不预设未确认的 API、数据库部署形态或运行依赖。

## Implementation Contract

- **基础代码位置：** 本票建立 `sci-weave/llm-wiki/`，含 `pyproject.toml`、独立 `uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/llm_wiki/`、`tests/`；`requires-python = ">=3.11"` 与现有 SciWeave Python 子项目保持一致。模块至少包含 `config.py`、`errors.py`、`canonical.py`、`domain.py`、`schema.sql`、`sqlite_store.py`、`terminus_store.py`、`resource_review.py`。
- **服务接口：** `ResourceReviewService.record_decision(resource_version_id, actor, decision, reason, evidence, scope, authority_context)` 只接受可信组合边界提供且可验证的 actor/authority context；查询接口 `get_current_qualification(resource_version_id, requested_scope)` 按追加序列和适用范围计算当前资格。直接 Resource Owner 通过精确 ResourceVersion 所属 Resource 的 `owner_id` 校验；代理审核人必须由注入的 `AuthorizationVerifier` 验证明确授权来源。`owner_id` 缺失、无验证器或授权不能证明时拒绝资格决定，保持 `pending` 并追加审计尝试；不建设未确认的外部身份服务，也不把自由文本或自报角色当授权证明。
- **权威与写入：** Wiki TerminusDB 持有精确 ResourceVersion 内容/元数据；提供 `TerminusStore.read_resource_version(location, resource_version_id)`，`location` 是 `ResourceVersionLocation(store_id, database, branch_id, commit_hash)`，必须来自写入该版本时固定的治理记录；结果必须包含精确目标 ID、所属 Resource、`owner_id`、可识别快照/摘要及未知字段。未知位置不得发起读取；精确版本不存在或结果不可确认时不作批准。SQLite 只保存 `ResourceVersionReview`、AuditEvent、稳定 ID 与版本资格决定；每项审核不可变追加，明确记录 actor、授权来源、决定、理由/证据、UTC 时间、范围/限制。未知身份、来源、许可、署名、哈希或访问限制必须作为未知事实记录，不能被解释为批准或可复现保证。
- **状态：** 无有效适用决定为 `pending`；当前有效决定按规格返回 `approved`、`rejected` 或 `revoked`。拒绝/撤回阻止新正式化；后续有效批准可恢复资格；内容变化的新 ResourceVersion 不继承旧决定。资格查询只返回状态和适用限制，不改写既有正式引用。
- **配置与验证：** `.env.example` 声明 `SCIWEAVE_WIKI_SQLITE_PATH`、`SCIWEAVE_WIKI_DOMAIN_ID`、`SCIWEAVE_WIKI_TERMINUSDB_URL`、`SCIWEAVE_WIKI_TERMINUSDB_DATABASE`、`SCIWEAVE_WIKI_TERMINUSDB_STORE`、`SCIWEAVE_WIKI_TERMINUSDB_TOKEN`。新增 `tests/test_resource_review.py`，以临时 SQLite、Fake TerminusStore 和 Fake AuthorizationVerifier 验证授权/越权、版本绑定、范围、未知证据、撤回与重批、追加审计；README 写 `uv sync --locked`、unittest 及本地 TerminusDB 集成命令。配置从 `.env` 注入，不能硬编码部署地址/端口/凭据。
- **依赖策略：** 仅 Python 标准库及仓库已有 TerminusDB 验证服务；如必须新增依赖，先建立依赖 fer 工单并记录来源、版本约束、用途、许可证/限制、安装和验证命令，再修改项目清单与锁文件。

## Acceptance Criteria

- [x] Python 子项目骨架、基础 SQLite/TerminusStore seam、独立锁文件和环境样例按上述路径建立；资源审核服务是后续 Wiki 纵向切片可复用的内部接口。
- [x] 资源资格决定以结构化追加记录保存，精确绑定不可变 `resource_version_id`，包含 actor、可验证授权来源、决定、证据、UTC 时间和适用范围/限制，并关联审计事件。
- [x] 仅 Resource Owner 或可验证的明确授权审核人可作出决定；缺少授权上下文、验证器或可识别身份时拒绝决定、维持 `pending` 并记录尝试。
- [x] 审核核对版本身份/快照、来源/生成信息、许可/署名、访问定位和处理方式；未知信息及外部内容未固定限制被显式保留，不可伪装为批准或复现保证。
- [x] 后续拒绝/撤回阻止该版本用于新正式化；后续有效批准可恢复资格；旧审核不覆盖，新的 ResourceVersion 不继承旧决定。
- [x] 候选与查询可按精确版本 ID 和使用范围获取当前资格；待审/拒绝/撤回不显示为批准，撤回不改写既有正式引用。
- [x] `tests/test_resource_review.py` 覆盖直接 Owner、授权审核人、越权、缺失授权、批准/拒绝/撤回/重新批准、范围限制、未知证据和追加审计；验证命令及实际结果回写本票。
- [x] 不引入未经确认的运行依赖；README 和环境变量不含真实凭据或固定部署端口。

## Notes

**2026-10-21T03:24:10Z**

已按 TDD 建立 `sci-weave/llm-wiki/`：独立 `pyproject.toml`、`uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/llm_wiki/` 与 `tests/`。实现包含 `config.py`、`errors.py`、`canonical.py`、`domain.py`、`schema.sql`、`sqlite_store.py`、`terminus_store.py`、`resource_review.py`；仅使用 Python 标准库，未新增依赖。

`ResourceReviewService.record_decision(...)` 将每条决定追加到 `resource_version_review`，精确绑定 `resource_version_id`，记录 reviewer、可验证授权来源、决定、理由/证据、UTC 时间、使用范围、限制、内容摘要、快照状态和未知事实，并追加 `wiki_audit_event`。直接 Resource Owner 通过精确版本所属 Resource 的 `owner_id` 校验；代理审核人必须由注入的 `AuthorizationVerifier` 验证。缺少 owner、授权上下文、验证器或验证失败时拒绝决定、保持 `pending` 并记录 `resource_review_attempt`。`get_current_qualification(resource_version_id, requested_scope)` 按追加顺序和范围计算当前资格；新 `ResourceVersion` 不继承旧决定。未知的许可、署名、内容哈希、来源、访问定位、可访问性和生成信息会作为 `unknown_facts`/`limitations` 保留。

实测命令与结果：

- `uv lock`、`uv sync --locked`：成功，CPython 3.11.14，editable install `sciweave-llm-wiki==0.1.0`。
- `uv run python -m unittest discover -s tests -v`：`Ran 22 tests ... OK (skipped=1)`。
- `uv run python src/main.py`：输出 `{"status":"ready",...,"reason_code":"exact_version_read_contract_unconfirmed"}`。
- `uv run python src/main.py demo-version`：输出 `pending` / `no_effective_decision`。

跳过项为 `tests/test_terminus_integration.py`，原因同上：本机无法拉取 TerminusDB 12.0.8 镜像，没有可用服务；该测试只断言失败关闭适配器绝不会返回 `confirmed`。`TerminusStore.read_resource_version(resource_version_id)` 的精确版本读取契约尚未取得与精确 Commit 等价的一手证据，因此具体适配器 `TerminusDBResourceStore` 显式返回 `unavailable` / `exact_version_read_contract_unconfirmed`，不猜测文档路径，也不回退到 branch head。

**2026-10-21T03:51:05Z**

本机 TerminusDB 服务已可用，集成测试不再是“跳过”。Compose 镜像 tag 修正为 `terminusdb/terminusdb-server:v12.0.8`（Docker Hub 无 `12.0.8`），容器启动后以 HTTP Basic `admin:<store-key>` 访问。

实测命令：`SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`（含 `SCIWEAVE_WIKI_TERMINUSDB_URL`/`DATABASE`/`STORE`）执行 `uv run python -m unittest discover -s tests -v`，结果 `Ran 22 tests ... OK`，其中 `test_unconfirmed_contract_never_returns_a_confirmed_version` 实际运行并通过，断言具体适配器即使连得上服务也不会返回 `confirmed`。

仍然阻塞的部分：`TerminusStore.read_resource_version(resource_version_id)` 只拿到不可变版本 ID，没有 `store/database/branch/commit` 身份；现有证据无法推导“按版本 ID 唯一定位精确快照”的读取路径（是否有索引文档、由哪个提交承载都未确定）。因此具体适配器继续显式返回 `unavailable`/`exact_version_read_contract_unconfirmed`，不猜测文档路径、不回退 branch head。本票保持 `in_progress`。

**未完成 / 阻塞：** Wiki ResourceVersion 的精确读取契约（版本 ID → 精确 store/database/branch/commit 的映射）尚未确认。该阻塞来自契约缺口，不再是服务不可用。

**2026-10-21T04:15:00Z**

按方案 A 解除上述阻塞。版本 ID 本身不解析位置，读取签名改为 `read_resource_version(location, resource_version_id)`：

- 新增 `ResourceVersionLocation(store_id, database, branch_id, commit_hash)`，由 `ExactVersionLocationSource` 注入，来源必须是写入该版本时固定的治理记录；位置未知时不发起读取，返回 `exact_version_location_unknown`，不猜测路径。
- `TerminusDBResourceStore` 复用 `research-mapping` 已验证的 `commit:` 文档路由，确认条件是响应头回显 `commit:<请求值>`、JSON 内容类型、返回列表中恰好一个文档匹配版本 ID（字段或 `@id` 后缀）。404/明确不存在为 `missing`；未知 Commit（本镜像实测 500）、响应头缺失/不符、非 JSON、连接失败均为 `unavailable`。
- 快照新增 `snapshot_digest`：对匹配到的版本文档按规范 JSON 计算 SHA-256，并随审核记录持久化；版本自身声明的 `content_checksum_value` 仍作为独立事实保留。
- 服务在批准、拒绝、撤回时都按同一精确位置读取；位置记录同时写入审核记录的 `target_location`。撤回在快照不可读时仍可追加，但不会虚构位置或摘要。

验证命令与结果（容器 `terminusdb/terminusdb-server:v12.0.8`，Basic `admin:root`，地址经环境变量传入）：

- `uv sync --locked`：`Audited 1 package`。
- `uv run python -m unittest discover -s tests`：`Ran 46 tests ... OK`。
- 集成用例（`SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`）自建 `<DATABASE>_it_<随机后缀>` 临时库，写入 `Resource` 与 `ResourceVersion` 并记录历史 Commit，随后更新同一版本的许可字段生成新 branch head；历史 Commit 读回原许可与原快照摘要，branch head 读回更新值，证明没有回退到最新版本；未知版本在可读 Commit 上返回 `missing`，未知 Commit 返回 `unavailable`。`Ran 46 tests ... OK`，无跳过。
- 契约与设计文档已同步：`docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md`（新增 Wiki 精确读取一节）、`docs/superpowers/specs/2026-10-20-mapping-wiki-implementation-readiness-design.md`、`docs/superpowers/plans/2026-10-21-mapping-wiki-vertical-slices.md`（该计划已由上述两份规格取代并移除，见文末更正）。

范围说明：候选/正式快照写入及位置记录属于后续切片；本票只固定读取 seam。未注入位置源时服务继续失败关闭，不批准任何版本。全部验收标准已满足，关闭本票。

**2026-10-21T04:49:00Z：复验集成测试**

按负责人确认后，使用本机运行中的 `terminusdb/terminusdb-server:v12.0.8` 重新执行 Wiki 集成验证。测试按随机名称创建临时数据库，分别验证历史快照读取、分支 head 更新、精确读取不回退、可读提交中缺失版本及未知 Commit 失败关闭；测试全部成功。运行后查询数据库列表，未发现残留的 Wiki 集成临时数据库。

- `uv sync --locked`：成功，`Audited 1 package`。
- `uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v`：`Ran 5 tests in 0.932s ... OK`。
- 测试使用的临时 `.env` 已删除；未修改票据状态。

**2026-10-21T05:10:00Z：更正已移除文档的引用**

上文 `2026-10-21T04:15:00Z` 一节把 `docs/superpowers/plans/2026-10-21-mapping-wiki-vertical-slices.md` 列为已同步文档。该计划已由 `docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md` 与 `docs/superpowers/specs/2026-10-20-mapping-wiki-implementation-readiness-design.md` 取代，并在 `feature/hanjiang` 的 `2e58a25` 中删除，路径不再存在；上方原句保留并加了标注，不删除历史记录。

- 当前有效依据只有两份规格：精确 Commit 读取契约（含 Wiki 按版本 ID 在固定位置内选取文档）与实现就绪设计（读取签名 `read_resource_version(location, resource_version_id)`）。
- 全量用例数复核：`sci-weave/llm-wiki/tests/` 为 `test_resource_review.py` 24 条、`test_terminus_store.py` 17 条、`test_terminus_integration.py` 5 条，合计 46 条，与上文 `Ran 46 tests ... OK` 一致。
- 票据状态不变，仍为 closed。
