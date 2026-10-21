---
id: ai4-vczt
status: open
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
- **权威与写入：** Wiki TerminusDB 持有精确 ResourceVersion 内容/元数据；提供 `TerminusStore.read_resource_version(resource_version_id)`，结果必须包含精确目标 ID、所属 Resource、`owner_id`、可识别快照/摘要及未知字段。精确版本不存在或结果不可确认时不作批准。SQLite 只保存 `ResourceVersionReview`、AuditEvent、稳定 ID 与版本资格决定；每项审核不可变追加，明确记录 actor、授权来源、决定、理由/证据、UTC 时间、范围/限制。未知身份、来源、许可、署名、哈希或访问限制必须作为未知事实记录，不能被解释为批准或可复现保证。
- **状态：** 无有效适用决定为 `pending`；当前有效决定按规格返回 `approved`、`rejected` 或 `revoked`。拒绝/撤回阻止新正式化；后续有效批准可恢复资格；内容变化的新 ResourceVersion 不继承旧决定。资格查询只返回状态和适用限制，不改写既有正式引用。
- **配置与验证：** `.env.example` 声明 `SCIWEAVE_WIKI_SQLITE_PATH`、`SCIWEAVE_WIKI_DOMAIN_ID`、`SCIWEAVE_WIKI_TERMINUSDB_URL`、`SCIWEAVE_WIKI_TERMINUSDB_DATABASE`、`SCIWEAVE_WIKI_TERMINUSDB_STORE`、`SCIWEAVE_WIKI_TERMINUSDB_TOKEN`。新增 `tests/test_resource_review.py`，以临时 SQLite、Fake TerminusStore 和 Fake AuthorizationVerifier 验证授权/越权、版本绑定、范围、未知证据、撤回与重批、追加审计；README 写 `uv sync --locked`、unittest 及本地 TerminusDB 集成命令。配置从 `.env` 注入，不能硬编码部署地址/端口/凭据。
- **依赖策略：** 仅 Python 标准库及仓库已有 TerminusDB 验证服务；如必须新增依赖，先建立依赖 fer 工单并记录来源、版本约束、用途、许可证/限制、安装和验证命令，再修改项目清单与锁文件。

## Acceptance Criteria

- [ ] Python 子项目骨架、基础 SQLite/TerminusStore seam、独立锁文件和环境样例按上述路径建立；资源审核服务是后续 Wiki 纵向切片可复用的内部接口。
- [ ] 资源资格决定以结构化追加记录保存，精确绑定不可变 `resource_version_id`，包含 actor、可验证授权来源、决定、证据、UTC 时间和适用范围/限制，并关联审计事件。
- [ ] 仅 Resource Owner 或可验证的明确授权审核人可作出决定；缺少授权上下文、验证器或可识别身份时拒绝决定、维持 `pending` 并记录尝试。
- [ ] 审核核对版本身份/快照、来源/生成信息、许可/署名、访问定位和处理方式；未知信息及外部内容未固定限制被显式保留，不可伪装为批准或复现保证。
- [ ] 后续拒绝/撤回阻止该版本用于新正式化；后续有效批准可恢复资格；旧审核不覆盖，新的 ResourceVersion 不继承旧决定。
- [ ] 候选与查询可按精确版本 ID 和使用范围获取当前资格；待审/拒绝/撤回不显示为批准，撤回不改写既有正式引用。
- [ ] `tests/test_resource_review.py` 覆盖直接 Owner、授权审核人、越权、缺失授权、批准/拒绝/撤回/重新批准、范围限制、未知证据和追加审计；验证命令及实际结果回写本票。
- [ ] 不引入未经确认的运行依赖；README 和环境变量不含真实凭据或固定部署端口。
