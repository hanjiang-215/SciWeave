# Research Mapping 与 LLM-Wiki 候选到正式化交付设计

- 日期：2026-10-21
- 负责人：hanjiang
- 范围：Research Mapping `ai4-6s53`、`ai4-z0lb`、`ai4-1qyc`；LLM-Wiki `ai4-91tk`、`ai4-txhf`、`ai4-jdjx`
- 状态：待用户审阅
- 依据：`2026-10-20-mapping-wiki-implementation-readiness-design.md`、Research Mapping 与 Wiki 各自跨存储正式化规格、`ai4-jnkn`

## 目标

沿现有依赖链补齐 Mapping 和 Wiki 的候选提交、候选审阅、正式化与失败恢复实现，并提供单元及真实 TerminusDB 验证。该交付由两个独立子项目组成，不合并治理边界，也不新增 Mapping/Wiki 之间的写依赖。

## 固定位置和依赖

代码位于当前中央侧目录：

- Research Mapping：`sci-weave/centre-control/research-map/`
- LLM-Wiki：`sci-weave/centre-control/research-wiki/`
- TerminusDB 验证服务：`sci-weave/centre-control/terminusdb/`

两个 Python 子项目保持独立的 `pyproject.toml`、`uv.lock`、SQLite 数据库、TerminusDB Store、审计链与环境配置。只使用各项目已锁定依赖（预期为 Python 标准库）和仓库固定的 TerminusDB 12.0.8；任何需要的新依赖必须先有依赖工单及来源、用途、版本约束、许可证/限制和验证命令，再变更项目清单与锁文件。

实施严格服从各自 fer 依赖顺序：

- Mapping：`ai4-mqtq` 已关闭 → `ai4-6s53` 候选提交 → `ai4-z0lb` 候选差异/审阅 → `ai4-1qyc` 正式化/恢复。
- Wiki：`ai4-vczt` 已关闭 → `ai4-91tk` 正式查询 → `ai4-txhf` 候选提交 → `ai4-jdjx` 审阅/正式化/恢复。

每条链逐票验收后再继续下游。两条链可独立执行，但本轮按 Mapping 链后 Wiki 链串行推进，避免共享环境和上下文切换导致验证证据混淆。每个工单仍单独记录实现和证据，不改变或代替工单中的验收契约。

## 不变量

1. SQLite 是该领域治理记录、当前正式指针、正式化状态和审计索引的权威；TerminusDB 是不可变内容快照和精确 Commit 的权威。SQLite 不复制图或 Wiki 正文。
2. 正式查询只返回 SQLite 当前指针、匹配的正式版本记录、成功正式化结果和精确 TerminusDB Commit 全部一致的内容。候选、未审批内容和未激活 Commit 永不通过正式查询暴露；任意不一致均失败关闭，不回退或前进到“最新”版本。
3. 正式化必须绑定固定 candidate head、精确基准、完整审核/批准证据及稳定 `formalization_operation_id`。只有 TerminusDB 精确 Commit 写入并读回确认后，才能进行 SQLite 本地原子激活；激活事务提交是唯一业务生效点。
4. SQLite 激活须以当前正式指针仍等于原基准为条件。更新正式版本、指针、成功结果及规格要求的来源处置在单一 SQLite 事务提交；事务失败不得部分生效。
5. 明确失败、结果未知、`graph_ready`（Mapping）或 `store_ready`（Wiki）、`reconciliation_required`、成功和通知失败必须区分。对未知状态先按原操作身份和精确 Commit 双侧读回对账；证据不足时不重写、不激活、不报告成功。重试沿用操作 ID/Commit 并增加 attempt，不创建重复正式版本。
6. Mapping 路线正式发布须有 Project Owner 对完整锁定方案的批准。Wiki 还须分别确认文档/引用审核、每个精确 ResourceVersion 当前有效且范围匹配的资源资格决定，以及 Project Owner Formal Publication Review；资源资格在激活前重新核验。
7. 不执行 SQLite 与 TerminusDB 跨存储回滚。未激活 Commit 保留为不可查询历史。通知在激活成功后发送，通知失败只记通知状态和审计，不撤销正式版本。
8. 所有变更依照 TDD：先增加一条行为测试并观察预期失败，再实现最小代码并运行目标测试和相关全套测试。真实 TerminusDB 用例须显式运行；默认跳过不算集成验证通过。

## 分阶段交付

### Mapping 候选提交（`ai4-6s53`）

在现有 `research-map` 代码上完成候选快照生产适配器和结果未知恢复。候选提交应在隔离分支基于精确正式 Commit 写入 TaskNode/DependencyEdge 快照，固定提交身份、提交者、基准、规范内容摘要和稳定候选定位；创建/重置分支及文档写入过程的任一超时都不能仅凭分支存在推断成功。按稳定 idempotency key 读回并验证候选的来源标记、base、完整内容及精确 Commit 后，才记录已确认候选治理事实；无法证明时返回 `result_unknown`，保留证据以供原身份对账，禁止重复创建逻辑候选。

保留现有候选校验（端点、版本/状态、自环、blocking 子图环）、正式基准检查和 SQLite 治理事务。使用临时 TerminusDB 数据库集成测试真实候选创建、隔离、精确 Commit 内容读回、重复请求以及可判定/不可判定的存储结果。实现后更新 `ai4-6s53` 证据并通过其验收再进入 `ai4-z0lb`。

### Mapping 候选审阅（`ai4-z0lb`）

在 `research_mapping/review.py` 提供面向固定 Proposal、正式基准和候选 head 的预览与 Merge Request Buffer 应用服务。通过 Mapping `TerminusStore.read_exact_snapshot` 读取精确基准及候选快照，生成稳定且可重复读取的字段级差异、受影响对象和路线影响证据；预览与 Buffer 均固定候选 Commit、base revision 和 preview/evidence ID。若正式基准前进、候选头不匹配、存储不可读或证据不完整，返回可审计的明确失败并阻止形成有效可批准请求。记录预审/审核操作者、UTC 时间、结论和理由；最终 Project Owner 批准和正式化留给 `ai4-1qyc`。

测试覆盖无变化、有效差异、重复读取、基准陈旧、候选不匹配/不可读、Buffer 固定输入和审计记录，并使用真实 TerminusDB 验证候选/正式 Commit 精确读取边界。

### Mapping 正式化与恢复（`ai4-1qyc`）

在 `research_mapping/formalization.py` 实现固定 Merge Request Buffer 的资格预检、授权 Project Owner 批准要求、TerminusDB 正式快照写入/精确读回、SQLite 条件激活、成功后通知及受控对账入口。采用 Mapping 专属的 `requested`、`in_progress`、`graph_ready`、`reconciliation_required`、`succeeded`、`failed` 状态；`graph_ready` 只表示图 Commit 已确认，仍不可查询。SQLite 激活事务同时创建 Formal MappingRevision、条件切换指针、写入成功 FormalizationResult，并完成成功所需的来源处置。恢复仅复用原操作、候选输入和精确 Commit；发现已激活则对账确认，仍旧基准时可在前置条件成立下重试原激活，证据不全或指针已前进则转受控对账/失败，不得覆盖新版本。

测试覆盖缺审批/越权/过期基准、成功、TerminusDB 明确失败和未知、SQLite 原子回滚与提交结果未知、Commit 已确认未激活后的恢复幂等、对账冲突及通知失败。集成测试验证真实精确图 Commit 与 SQLite 激活边界。

### Wiki 正式内容查询收尾（`ai4-91tk`）

核查现有 `WikiFormalQueryService` 与真实 TerminusDB 服务级集成证据，补齐资源版本引用通过真实 `ResourceReviewService` 按精确版本 ID/范围返回当前资格的端到端测试；资格状态未知、待审或撤回时保持原引用 ID 并显式提示。重新运行单元测试、正式查询真实服务集成和资源版本精确 Commit 集成后，才关闭该票。

### Wiki 候选提交（`ai4-txhf`）

在 `llm_wiki/candidate_submission.py` 接纳完整 WikiDocument 正文、结构化属性和完整 Resource Reference 集合；逐引用核验领域和精确版本 ID，禁止隐式解析最新版本或跨 Proposal 非法目标。对待审/拒绝/撤回资源允许留在隔离候选，但真实显示其资格，并阻止进入可供 Owner 审核/正式化的有效请求。候选提交使用隔离 Proposal/candidate head、稳定幂等身份及规范内容摘要；写入 TerminusDB 后必须读回精确候选并对账，确认后才在 SQLite 原子写入 Submission、Proposal、CandidateCommit 和审计。未知结果按同一身份对账，不覆盖其他候选。

测试覆盖完整引用单元、非法目标、过期基准、幂等重复/冲突、资格门槛、存储明确失败与未知；真实服务集成验证隔离候选及精确版本读回。

### Wiki 审阅、正式化与恢复（`ai4-jdjx`）

在 `llm_wiki/review.py` 和 `formalization.py` 完成固定候选的差异/冲突预览、文档/引用审核、Merge Request Buffer、Project Owner 选择/批准/驳回及审计；资源资格审核不得与文档审核或 Owner 批准合并。正式化使用 Wiki 专属 `requested`、`in_progress`、`store_ready`、`reconciliation_required`、`succeeded`、`failed` 状态，精确 TerminusDB Commit 写入并读回后方可进行 SQLite 原子激活；激活事务再次核对基准、资源批准决定及其范围仍有效，并同时建立 FormalWikiRevision、条件切换指针、成功结果（含资源批准决定 ID）和来源处置。资源批准变化后必须重新审核并重新取得 Owner 批准及操作身份；未知结果仅复用原操作与精确 Commit 对账；通知失败不回滚成功。

测试覆盖冲突/无冲突、候选/基准失效、Owner 驳回/批准、资源批准撤回、TerminusDB 和 SQLite 明确失败/未知、原子回滚、恢复幂等、激活对账和通知失败。真实 TerminusDB 集成验证候选与正式快照内容和精确 Commit 身份。

## 验证与工单证据

两个子项目各自执行 `uv sync --locked`、`uv run --env-file .env python -m unittest discover -s tests -v`，以及针对当前切片显式运行的真实 TerminusDB 集成测试。测试使用系统临时目录/数据库，不依赖固定部署端口；不得提交 `.env`、真实凭据、缓存、虚拟环境或构建产物。每张工单记录确切命令、测试数、跳过情况、真实服务是否运行、结果未知的验证证据和未完成限制；不将默认跳过表述为通过。最终运行 fer 依赖无环检查与 ticket-index 校验；只由当前 assignee 修改本人负责的工单。

## 范围外

本轮不新增外部 API/MCP/Web、跨域共享包、跨 Mapping/Wiki 事务、身份服务、消息通知传输系统、其他数据库/队列、第三方 Python 依赖或部署拓扑；不修改 `ai4-xup8` 地图票和不属于当前负责人维护的工单。已存在的 `ai4-6s53` 未提交修改必须先复核并保留，不得覆盖或丢弃。
