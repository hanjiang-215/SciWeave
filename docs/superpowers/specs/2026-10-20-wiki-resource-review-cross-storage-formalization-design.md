# Wiki 资源审核与跨存储正式化设计

- 日期：2026-10-20
- 关联工单：[`ai4-7xtf`](../../../.tickets/ai4-7xtf.md)
- 依据：[`LLM-Wiki 内容模型`](./2026-10-19-llm-wiki-content-model-design.md)、[`Wiki 候选治理记录模型`](./2026-10-19-wiki-candidate-governance-record-model-design.md)、[`Wiki Proposal 与 Merge Request Buffer 生命周期`](../../../.tickets/ai4-zewm.md)
- 状态：领域决策已确认；待后续实现工单引用

## 目的与边界

本设计收敛 LLM-Wiki 中 ResourceVersion 的正式引用资格、资源审核与文档审核分工，以及 Wiki TerminusDB 内容存储和 SQLite 治理记录之间的正式化、失败恢复和查询语义。本文定义产品和领域事实，不指定 API、代码结构、SQLite DDL、TerminusDB Schema、SDK、部署方式或外部运行依赖。

Wiki 与 Research Mapping 保持独立的 MCP、Buffer、Proposal、存储、Revision 和审计链。本文只复用跨存储治理中的通用原则；不把 Mapping 的 TaskNode、Dependency Edge、调度或其他领域规则移植为 Wiki 规则。

## 资源审核与 Wiki 文档审核

### 责任分工

资源资格审核和 Wiki 文档/引用审核是两项不同的治理决定：

- Resource Owner 或其明确授权的审核人，对一个精确、不可变的 `ResourceVersion` 作出资源资格决定。授权范围须能追溯；没有可识别的负责人或授权审核人时，资源保持待审，不能获得正式引用资格。
- Wiki Curator 或文档负责人审核 Wiki Submission 的正文及其引用是否适切。该审核不代表资源版本的来源、许可或治理资格已获批准。
- Project Owner 对锁定候选方案执行既有 Formal Publication Review。它既不替代资源资格审核，也不替代 Wiki 首阶段文档/引用审核。
- 同一人可以兼任多个角色，但每项决定必须依照各自授权分别作出、分别记录；一项决定不能推定或代替另一项。

### ResourceVersion 资格决定和证据

每次资源审核形成一条独立、追加式的结构化审核决定记录，至少包括：

- `resource_version_review_id`：该审核决定的稳定身份；
- `resource_version_id`：精确的、不可变的审核目标；
- `reviewer_id` 与 `authority_reference`：审核人及其 Resource Owner/授权来源；
- `decision`：`approved`、`rejected` 或 `revoked`；
- `reason` 与 `evidence_reference`：决定依据、证据摘要或可追溯证据引用；
- `decided_at`：决定时间；
- `use_scope` 与 `limitations`：有条件批准时允许的引用/使用范围和限制。

该审核决定作为 Wiki 治理中的独立结构化记录保存，并以稳定 ID 关联对应 WikiAuditEvent；仅有自由文本审计备注不足以代替精确版本资格记录。

审核证据应足以回答以下问题：

1. 版本身份和内容是否可以被识别；有上游不可变版本标识、内容快照哈希或相应来源证据时，应记录它们。
2. 来源、生成者/时间以及可用的输入关系是否可追溯。
3. 许可、署名和使用限制是否有记录；确实不清楚的事项应明确标为未知，不能伪装成已确认。
4. 访问定位和 `handling_mode` 是否明确；需要人工处理的资源应说明必要的处理方式。

这项审核决定的是资源版本能否在已记录范围内获得正式引用资格，不是对资源科学质量的同行评审，也不评判它是否适合某一篇具体 Wiki 文档。文档适切性由 Wiki 审核人判断。

许可或权利信息未知、或外部内容无法固定时，审核人可以给出范围受限的批准，但必须清楚记录限制并在展示中提示：

- 许可状态不明确时，可以批准仅指向资源的引用/元数据记录；这不等于允许复制、托管或再分发资源内容。超出已批准用途范围的处理不满足该决定。
- 外部资源没有稳定上游版本 ID 且无法取得内容快照哈希时，可以批准本次内部 `ResourceVersion` 引用记录；必须明示该记录不能证明外部内容已固定，也不能据此宣称内容可复现。

每次重新审核、更正或撤回都追加新记录，不覆盖既有决定。某版本当前资格按该版本审核记录的追加顺序读取最新有效决定：批准使其在记录的使用范围内满足后续正式化检查；拒绝或撤回使其不满足；后续新批准可以恢复该版本未来正式引用资格。

### 候选引用、正式化门槛及撤回

- 候选 WikiRevision 可以包含精确指向待审 ResourceVersion 的引用，以便在 Proposal 中准备和审查；候选预览必须标出待审/被拒等资格状态，且不能作为已批准资源或正式内容展示。
- 资源资格审核可独立于 Wiki Submission 接纳审核进行。资源仍待审、被拒、已撤回或批准范围不覆盖该用途时，候选不得进入 Project Owner Formal Publication Review 或正式化。
- Project Owner Formal Publication Review 开始前，候选中每个 `target_resource_version_id` 都必须有当前有效、绑定同一版本且覆盖引用用途的资源批准记录。资源审核结论与证据引用随正式化治理记录可追溯。
- ResourceVersion 内容变化必须创建新版本并重新审核；不继承旧版本决定。对同一版本重新审核只有通过追加批准决定才可恢复资格。
- 撤回不追溯改写已经正式化的 WikiRevision、引用目标或 Formal WikiRevision 历史指针；撤回后该版本不能用于新的正式化。既有正式查询保留精确原引用，可显示当前资格已撤回的状态提示。修订既有内容须提交新的 WikiRevision，并引用其他当前有资格的版本。

## Wiki 正式化边界

### 前置条件与顺序

正式化依次满足以下条件和步骤：

1. Wiki Proposal/Merge Request Buffer 锁定精确 candidate head、基准 `base_formal_revision_id` 和完整候选审阅范围。锁定后的 head 不移动、不追加写入。
2. 在 Project Owner 审核开始前，检查每个资源引用对应的 ResourceVersion 是否有当前有效且范围适配的资源批准。资源待审、被拒、撤回或证据绑定到其他版本时，阻止进入该阶段。
3. Project Owner 对该锁定的完整候选方案和固定基准作出 Formal Publication Review，并留下独立批准 AuditEvent。候选基准必须仍是当前 Formal WikiRevision。
4. 创建稳定的 `formalization_operation_id`，保存操作意图和本次尝试记录；在任何正式激活前，普通 Formal Query 继续读取当前正式版本。
5. 将锁定候选的精确内容写入 Wiki TerminusDB 的正式存储位置，并读回确认实际 Store、Commit 身份、候选来源和内容/引用快照与锁定方案一致。TerminusDB Commit 仅证明存储变化，不代表业务批准或正式生效。
6. 确认 TerminusDB 精确 Commit 后，SQLite 执行一个本地原子激活单元：创建 `Formal WikiRevision` 记录，条件切换当前正式版本指针，记录成功的 `WikiFormalizationResult`（包括每个被引用 ResourceVersion 对应的当前批准决定 ID），并同步完成成功依赖的 MR/Proposal 状态及来源最终处置。激活单元须再次确认当前正式基准未变化，且所有资源资格决定仍是当前有效、范围适配的批准；若 PO 审核后资源决定已撤回/更改，则阻止激活，先重新完成相关资源审核，再取得新的 PO 审核批准和正式化操作身份。
7. 只有上述 SQLite 激活单元提交后，正式化才算业务成功。Project Owner 批准、TerminusDB Commit 创建或读回成功，单独都不构成成功。
8. SQLite 激活确认成功后发送通知。通知失败只更新独立通知记录，不撤销正式化。

激活必须以 `current_formal_revision_id == base_formal_revision_id` 为条件。若正式基准在校验后、SQLite 激活前已前进，激活失败，旧候选不得覆盖新版本；操作阻塞并要求基于最新 Formal WikiRevision 创建新的 Submission/Proposal、候选和审核请求。已经写入但未激活的 Commit 保留为不可查询历史。

### 操作身份、结果和状态

每个逻辑正式化操作具有稳定的 `formalization_operation_id`。它绑定 Wiki domain、Merge Request、所选完整方案、锁定 candidate head、基准 Formal WikiRevision 和 Project Owner 批准事件。每次执行尝试有独立结果记录和递增的 `attempt_number`。相较既有 Wiki 治理记录模型，`WikiFormalizationResult` 需补充操作 ID、尝试序号及本设计中的结果状态，并在成功时追踪精确 TerminusDB Commit、正式 Revision 和所引用资源版本的当前批准决定 ID；这只是领域字段要求，不规定数据库 DDL。相同输入的重复请求复用操作身份，不生成第二个 Formal WikiRevision；candidate head、正式基准、批准决定或所选方案改变时创建新操作。

正式化逻辑状态采用：

- `requested`：前置资格通过，操作意图已记录，尚未完成存储写入；
- `in_progress`：正在执行一次正式化尝试；
- `store_ready`：精确 TerminusDB Commit 已读回确认，SQLite 尚未激活；
- `reconciliation_required`：存储结果、SQLite 激活结果或两侧关联无法确认，禁止查询新版本和盲目重试；
- `succeeded`：SQLite 激活单元持久化成功，是唯一可供 Formal Query 使用的结果；
- `failed`：该次尝试发生了可确定失败，且尚未激活正式版本。修复后可在输入未变时增加 attempt 重试；输入或批准范围变化则创建新操作。

失败/尝试历史不删除。对同一操作最多有一个成功 FormalizationResult。治理状态变化、每次尝试和恢复均可由追加 AuditEvent 追溯。

## 跨存储失败与恢复

| 情况 | 正式查询可见性 | 处理规则 |
| --- | --- | --- |
| 前置审核缺失、资源不合格或候选基准已过期 | 仍为原 Formal WikiRevision | 不开始正式写入或激活；记录阻塞/失败原因。基准过期时必须重新基于最新正式版本提交和审核。 |
| TerminusDB 在 Commit 产生前明确失败 | 仍为原 Formal WikiRevision | 追加失败尝试。修复可重试同一操作及相同输入；尝试号递增。 |
| TerminusDB 写入响应丢失或结果未知 | 不显示新版本 | 先按操作身份、锁定 head 和存储证据读回确认。精确 Commit 已存在则复用；能够确认没有写入才重试；不能证明写入与否则进入 `reconciliation_required`，不得盲目重写或激活。 |
| TerminusDB Commit 已确认，SQLite 激活明确失败 | 仍为原 Formal WikiRevision | 记录 `store_ready` 或失败尝试，保留该精确 Commit；重试使用同一操作和同一 Commit，不新建内容版本。 |
| SQLite 激活结果未知 | 暂不宣称新版本成功 | 按操作身份读取 Formal WikiRevision、当前指针、成功结果和正式 Commit 关联。全部吻合且 Commit 可读时确认既有成功；若仍是旧指针且激活前置条件成立，可重试同一 Commit 的 SQLite 激活；部分记录或结果仍不明时进入 `reconciliation_required`。 |
| SQLite 指针、FormalizationResult、批准证据、基准或 TerminusDB Commit 不匹配 | 返回不可用/需对账；不返回未确认新版本 | 保留冲突证据和历史，不覆盖或静默选择最新版本。经受控对账/授权人工恢复并追加审计后才可恢复查询或启动新操作。 |
| 重复正式化请求 | 读取原操作状态 | 按稳定操作身份返回既有状态/结果；不创建重复 Formal WikiRevision。 |
| 正式化成功、通知失败 | 新正式版本仍然有效 | 通知状态单独记录并可重试；不得回滚或改写正式化结果。 |

跨存储不执行回滚或物理删除。未激活的 TerminusDB Commit 永远不能仅凭存在而进入 Formal Query。对账、人工恢复、指针修正、重试决定或操作终止均追加 AuditEvent 并保留原始结果记录。

## 正式查询权威

- SQLite 的当前正式指针、对应 Formal WikiRevision 和成功 FormalizationResult 决定哪个 Wiki 版本已激活。
- Formal WikiRevision 记录所指向的精确 TerminusDB Store/Commit 决定该正式版本的正文、结构化关系和引用快照；禁止按 branch 的“最新 Commit”推断。
- 若 TerminusDB 已有未激活的新 Commit，但 SQLite 当前指针和其关联的旧正式 Commit 仍精确匹配且可读，正常查询继续返回旧正式版本；未激活 Commit 不可见。
- 若 SQLite 指针/成功记录与其精确 Commit 不匹配，或该 Commit 不可读，则返回明确的正式版本不可用/需对账结果，不回退到其他版本，也不读取候选内容。
- `requested`、`in_progress`、`store_ready`、`reconciliation_required` 和 `failed` 均不具备新版本正式查询资格。普通查询仅暴露已成功激活的 Formal WikiRevision。
- 正式 WikiRevision 中的资源引用仍解析到原精确 ResourceVersion ID；资源资格后来撤回时，可以展示状态提示，但不自动改指新版本，也不改写历史正文/引用。

## 审计记录

WikiAuditEvent 以追加式方式记录至少以下事实：资源审核/授权/批准/拒绝/撤回决定及其精确 ResourceVersion；Wiki Submission 接纳审核；MR head 锁定；Project Owner 批准/拒绝及所选方案；formalization operation 与 attempt 建立；TerminusDB 写入/读回结果及精确 Commit；SQLite 激活、成功/失败/结果未知；基准冲突、对账、人工恢复或指针修正；通知投递失败和重试。事件记录操作者/执行主体、时间、目标稳定 ID、决定/结果、原因，并能关联对应审核证据、正式化操作和尝试。更正通过新事件表达，不覆盖历史。

## 与 Research Mapping 治理规则的关系

可复用的通用原则包括：锁定候选头、审批不等于正式化成功、跨存储只认精确版本身份、以一个本地原子激活单元确定生效、稳定操作身份与幂等重试、未知结果先对账、不执行跨存储回滚、未激活内容隔离，以及查询在不一致时失败关闭。

不得移植 Mapping 专属的 TaskNode/Dependency Edge、调度语义、Mapping 领域状态或数据库记录。Wiki 独立维护 WikiProposal、WikiRevision、ResourceVersion、WikiAuditEvent 和自己的查询/恢复语义；没有跨 Mapping/Wiki 原子事务，也不共享 MCP 或审计链。

## 场景验证

1. **候选引用待审资源**：可保存精确 ResourceVersion 引用并显式显示待审；不能进入 Project Owner Formal Publication Review 或 Formal Query。资源审核后重新运行资格检查。
2. **资源已批准但文档引用不合适**：Wiki Curator/文档负责人可拒绝文档/引用；资源决定仍是独立事实，不自动变成文档批准。
3. **许可未知或外部内容未固定**：仅可按审核记录中的限定用途批准；显式提示未知许可、引用范围和不可复现限制，不能宣称允许复制/再分发或已固定内容。
4. **资源资格撤回**：阻止该版本用于未来正式化；既有 WikiRevision 保留原引用并显示资格状态提示，不静默切换目标版本。
5. **TerminusDB 已写入、SQLite 尚未激活**：普通查询仍返回旧的、精确 Commit 可读的正式版本；新 Commit 留在不可查询历史。
6. **SQLite 激活回执丢失**：按稳定操作 ID 对账；确认本地激活完整提交后确认成功，否则保持不可用/需对账，不盲目重复创建。
7. **候选基准已前进**：SQLite 条件激活失败，旧候选不覆盖新版本；基于最新 Formal WikiRevision 创建新的完整候选方案并重新审核。
8. **通知失败**：正式版本继续有效；通知独立记录失败原因和重试结果。

## 依赖

本设计不引入源码、构建流程、外部服务或运行时依赖，不需更新 `docs/DEPENDENCIES.md` 或新增包锁文件。后续若实现需要新增依赖，必须先在对应 fer 任务中记录用途、来源、版本约束、许可证/使用限制及验证命令，再按所属子项目包管理器声明和锁定。
