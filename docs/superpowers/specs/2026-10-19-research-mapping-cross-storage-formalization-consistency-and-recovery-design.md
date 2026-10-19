# Research Mapping 跨存储正式化一致性与失败恢复设计

- 日期：2026-10-19
- 关联工单：[`ai4-azx2`](../../../.tickets/ai4-azx2.md)
- 相关规格：[`Research Mapping 内容持久化模型`](./2026-10-19-research-mapping-content-persistence-model-design.md)、[`Research Mapping 候选治理记录模型`](./2026-10-19-research-mapping-candidate-governance-record-model-design.md)
- 状态：施工前领域规格已收敛

## 目的与边界

本设计定义 Research Mapping 正式化同时涉及 TerminusDB 与 SQLite 时的产品级一致性语义、可见状态、幂等重试、补偿和查询规则。它解决的是“什么状态才算正式化成功”和“跨存储结果无法同时确认时产品如何表现”，不规定具体事务实现、API、消息队列、SQL、TerminusDB Schema、部署方式或网络重试库。

存储职责保持分离：

- **Research Mapping Store（TerminusDB）**持有 TaskNode、DependencyEdge 及候选/正式图快照的正文和精确 Commit。TerminusDB Commit 证明图存储发生过一次变更，但不证明该变更已经批准或进入正式查询。
- **Research Mapping 治理记录（SQLite）**持有 Proposal、Merge Request Buffer、批准审计、FormalizationResult、Formal MappingRevision 的治理索引和 `current_formal_revision_id`。SQLite 不复制图正文。
- **Formal MappingRevision**是产品层的正式版本身份，必须同时引用 Project Owner 批准事实、候选来源、精确 TerminusDB Commit 和 SQLite 当前正式指针。TerminusDB 或 SQLite 的单独记录都不能独立构成正式版本。

## 核心不变量

1. Project Owner 对固定 Merge Request Buffer 和候选方案的批准是正式化的必要条件，但批准本身不等于正式化成功。
2. 正式化只能针对锁定的 candidate head、固定的 `base_formal_revision_id` 和固定的批准审计事件进行。当前正式指针已经前进时，旧候选必须标记为过期或阻塞，不能静默重放。
3. 新的 Formal MappingRevision 只有在 TerminusDB 精确图快照已经写入并读回确认，且 SQLite 的正式版本、当前指针和成功结果在同一个本地激活单元中持久化后，才可以成为当前正式版本。
4. `current_formal_revision_id` 是正式查询的激活闸门。候选 Commit、TerminusDB formal branch 上尚未完成治理关联的 Commit、以及只有批准记录但没有成功 FormalizationResult 的方案，都不能进入正式查询或正式调度。
5. 一个 `mapping_domain_id` 同时至多有一个当前正式指针。正式指针更新必须以旧的 `base_formal_revision_id` 为条件，不能覆盖其他正式化操作已经建立的新版本。
6. 发生失败、超时、部分完成或无法确认时，历史记录和存储 Commit 不删除、不原地改写；通过新的审计事件、重试尝试或补偿记录表达后续处理。
7. 查询正式状态采用两侧交集：SQLite 决定哪个 Formal MappingRevision 被激活，TerminusDB 决定该 Formal MappingRevision 所引用的图内容。任一侧无法证明精确匹配时，查询必须报告不可用或不一致，不能返回候选内容，也不能静默换用另一个版本。

## 正式化业务流程与确认边界

以下是产品可观察的逻辑顺序，不要求实现采用某一种跨存储事务技术。

### 1. 资格确认

正式化尝试开始前，必须确认：

- Merge Request Buffer 的候选 head 已锁定；
- Project Owner 已对该完整候选方案产生明确批准 AuditEvent；
- Proposal、Merge Request Buffer、CandidateSolution 的基准正式版本一致；
- 当前 `current_formal_revision_id` 仍等于候选的 `base_formal_revision_id`；
- 候选 Commit、影响范围、审核证据和来源处置记录可定位。

资格确认失败时不写入新的正式图快照，FormalizationResult 以 `failed` 记录原因；如果是基准过期，Merge Request Buffer 和 Proposal 进入既有的 `stale` 或等价阻塞状态，必须从最新正式版本重新生成候选。

### 2. 建立正式化操作身份

系统为一次完整正式化操作生成稳定的 `formalization_operation_id`，并以以下组合建立幂等约束：

- `mapping_domain_id`；
- `merge_request_id`；
- `selected_solution_id`；
- 锁定的 `candidate_head_commit_hash`；
- `base_formal_revision_id`；
- Project Owner 批准 AuditEvent。

同一操作的重试沿用同一个 `formalization_operation_id`，只增加 `attempt_number`，不得因为网络重试创建第二个逻辑 Formal MappingRevision。候选 head、批准方案或正式基准发生变化时，必须创建新的正式化操作身份。

SQLite 先记录操作意图和进行中的尝试，但此时不创建可查询的当前正式版本；记录意图不改变 `current_formal_revision_id`。

### 3. 生成并确认 TerminusDB 图快照

TerminusDB 根据锁定的候选方案生成或确认正式图快照，并返回精确的 `formal_branch_id`、`formal_commit_hash` 及必要的快照校验信息。平台必须读回并确认：

- Commit 确实存在于预期的 Research Mapping Store；
- Commit 对应锁定的候选 head 和批准方案；
- 图快照的节点、边和版本引用满足正式 Mapping 的约束；
- 快照没有把未批准的候选内容混入正式图。

确认成功后，FormalizationResult 进入 `graph_ready`。该状态表示“图快照已准备好”，不表示已经正式化；此时 `current_formal_revision_id` 仍保持原值，Formal Query 仍读取原正式版本。

### 4. SQLite 正式版本激活

只有完成 TerminusDB 精确 Commit 确认后，治理记录才可以执行本地激活单元。该单元必须以旧的 `base_formal_revision_id` 等于当前指针为条件，并一次性持久化：

- 新的 Formal MappingRevision，包含精确 Store、branch、Commit、来源 Proposal、Merge Request 和批准事件；
- `current_formal_revision_id` 从基准版本切换到新版本；
- 本次尝试的 `FormalizationResult.result_status = succeeded`，并关联 `formal_revision_id` 和精确 `formal_commit_hash`；
- Merge Request Buffer 和 Proposal 的 `merged` 状态，以及来源 CandidateCommit 的最终处置。

该本地激活单元的持久化提交是业务唯一生效点。执行前已确认的 TerminusDB Commit 是必要前置条件；SQLite 激活单元提交成功即满足正式化成功条件。通知不属于该单元。若该单元的提交结果无法确认，调用方不能自行报告成功或创建新的 Formal MappingRevision，必须按操作身份读取实际持久状态并对账。

### 5. 激活确认与结果未知恢复

正常收到 SQLite 激活单元已提交的确认后，本次尝试为 `succeeded`。若确认丢失或 SQLite 暂时不可读，使用同一个 `formalization_operation_id` 检查持久记录：

- 若 SQLite 显示新 Formal MappingRevision、当前指针、成功 FormalizationResult 和来源信息均匹配，且 TerminusDB 精确 Commit 仍存在并匹配，则将操作确认为成功，不重复写入；
- 若 SQLite 仍保留旧指针而 TerminusDB Commit 已准备好，则以同一操作、同一 Commit 再尝试本地激活；
- 若 SQLite 只完成部分写入、正式指针与结果状态不一致，或任一侧无法证明匹配，则报告 `reconciliation_required`，Formal Query 不返回新图内容，进入受控对账。

SQLite 激活单元内部的原子可观察性是领域要求，不绑定具体事务 API。对账不得仅凭一次写入调用的返回值、本地缓存或 branch 名称推断成功。

### 6. 通知

通知发生在正式化成功确认之后。通知投递失败只更新 MappingNotification 的投递状态并追加 AuditEvent，不回滚或撤销已经成功激活的 Formal MappingRevision。通知可以独立重试，不能被视为正式化成功条件。

## FormalizationResult 状态

`MappingFormalizationResult` 的 `result_status` 使用以下产品语义：

| 状态 | 含义 | 正式查询是否读取新版本 | 后续动作 |
| --- | --- | --- | --- |
| `requested` | 已通过资格确认并建立正式化操作，但尚未完成图存储处理 | 否 | 开始或恢复同一操作 |
| `in_progress` | 正式化正在执行，最终结果尚未确认 | 否 | 继续执行或根据超时规则转入恢复 |
| `graph_ready` | 精确 TerminusDB 图快照已确认，SQLite 激活尚未确认 | 否 | 使用同一操作身份完成激活或恢复 |
| `reconciliation_required` | 两侧结果无法证明一致，或已出现未激活的图 Commit | 否 | 运行受控对账；未完成对账前禁止正式化新版本 |
| `succeeded` | Formal MappingRevision、当前正式指针和 TerminusDB Commit 均已双侧确认 | 是 | 发送通知并完成来源处置 |
| `failed` | 在产生可激活正式图快照前发生的确定性失败 | 否 | 修复原因后沿用同一操作身份重试，或由审核者放弃 |

`succeeded` 写入 SQLite 激活单元的同一持久化提交中；其前置条件是精确 TerminusDB Commit 已在该激活前被读回确认。FormalizationResult 每个尝试使用独立的 `result_id`，同一正式化操作的尝试共享 `formalization_operation_id` 并递增 `attempt_number`；重试不删除旧尝试。SQLite 激活确认丢失时，对账读取已提交的结果，不能再创建一条重复的成功版本。

以下状态关系必须保持：

- `requested` → `in_progress` → `graph_ready` → `succeeded` 是正常路径；
- `in_progress` 在没有可激活图快照时可以进入 `failed`；
- `in_progress` 或 `graph_ready` 在结果未知、双侧不一致或恢复所需证据不足时进入 `reconciliation_required`；
- `failed` 是某次尝试的终态，仅用于未产生可激活图快照的确定性失败；修复后新建更高 `attempt_number` 的尝试，但仍沿用同一 `formalization_operation_id`；
- `succeeded` 是唯一成功终态；若其持久化提交确认丢失，通过对账读取既有成功记录，不回写状态也不再创建版本。

## 失败、重试与补偿规则

| 场景 | 可见结果 | 当前正式指针 | 恢复规则 |
| --- | --- | --- | --- |
| 基准过期、候选验证失败或批准缺失 | `failed`，并记录原因 | 保持原值 | 候选标记过期/阻塞；重新生成候选并重新审核 |
| TerminusDB 在产生 Commit 前失败 | `failed` | 保持原值 | 修复原因后沿用同一操作身份重试 |
| TerminusDB Commit 已确认，但 SQLite 不可用或激活失败 | `graph_ready` 或 `reconciliation_required` | 保持原值或状态不可确认；不得宣称新版本正式 | 重用同一精确 Commit 完成激活；禁止新建重复正式版本 |
| SQLite 激活结果未知 | `reconciliation_required` | 不以本地缓存推断 | 先按操作身份读取两侧状态；若无法证明匹配，保持不可查询并转人工/受控恢复 |
| 双侧字段、Commit hash、基准或批准事件不匹配 | `reconciliation_required` | 不把不匹配版本视为正式 | 保留冲突证据，修复治理记录或重新生成候选；不得静默覆盖 |
| 重试请求重复到达 | 返回原操作的当前结果 | 不产生第二个正式版本 | 按 `formalization_operation_id` 和精确候选 head 幂等读取 |
| 正式化成功但通知失败 | `succeeded`；Notification 为 `failed` | 已切换到新值 | 独立重发通知；不回滚正式版本 |
| 对账发现已有图 Commit 但没有正式治理记录 | `reconciliation_required` | 不指向该 Commit | 将 Commit 作为未激活历史保留；只有通过原操作身份和完整审批校验后才能继续激活 |
| 对账发现当前指针指向不存在或不匹配的 Commit | `reconciliation_required` | 正式查询返回不一致/不可用 | 冻结该领域的新正式化；经授权审计修复后再恢复查询 |

补偿的最小保证是“隔离而不误发布”：未确认的图 Commit 可以保留在存储中供对账，但永远不能仅凭其存在进入 Formal Query。首版不要求删除 Commit 或跨存储回滚；任何指针修复、正式记录修复或重新激活都必须有新的 AuditEvent，并引用原始 FormalizationResult。

自动恢复只允许在以下条件同时满足时继续：操作身份、候选 head、基准版本、批准事件和精确 Commit 全部一致，且当前正式指针没有被其他正式化操作前进。其他情况必须进入受控对账或人工判断，不能自动选择“最新”记录。

## 不一致时的查询权威

### 正式资格

SQLite 的 `current_formal_revision_id` 和对应的 Formal MappingRevision 是“哪个产品版本被激活”的权威。批准事件、来源方案、基准版本和正式化结果也以 SQLite 治理记录和 AuditEvent 为权威。

### 图内容

TerminusDB 中由 Formal MappingRevision 精确引用的 `formal_branch_id + formal_commit_hash` 是“该正式版本包含什么图内容”的权威。不能从 branch 名称、最新 Commit 或候选 head 推断正式内容。

### 查询行为

Formal Query 必须先读取 SQLite 当前指针，再定位对应的精确 TerminusDB Commit，并完成匹配校验：

1. SQLite 当前指针仍是旧版本，而 TerminusDB 已经存在一个尚未关联的新 Commit：返回旧的当前正式版本；新 Commit 不可见。
2. SQLite 当前指针和 Formal MappingRevision 已更新，且 TerminusDB 精确 Commit匹配：返回新正式版本。
3. 当前指针、Formal MappingRevision 和 TerminusDB Commit 任一不匹配，或精确 Commit 不可读：返回明确的“正式版本不可用/需要对账”结果，不返回候选内容，也不静默退回或前进到其他版本。
4. 查询只读取 `succeeded` FormalizationResult 关联的 Formal MappingRevision；`requested`、`in_progress`、`graph_ready` 和 `reconciliation_required` 都不具备正式查询资格。

该规则优先保证未批准数据不进入正式查询；可用性下降时，以显式不可用替代隐式返回未确认内容。

## 审计要求

每次正式化操作至少追加以下事件，并全部携带 `formalization_operation_id`、`result_id`、`mapping_domain_id`、操作者/执行主体、时间、基准正式版本和结果：

- 资格确认或拒绝；
- 候选 head 锁定；
- TerminusDB Commit 创建、读回确认或失败；
- Formal MappingRevision 创建和当前指针激活；
- 双侧确认成功或不一致；
- 重试、对账、补偿、人工放弃；
- 通知创建、投递失败或重发。

审计事件追加后不可删除或原地改写。错误更正必须追加引用原事件的新事件；对账结果必须保留发现的两侧值和采取的处理理由。

## 场景检查

1. **首次正式化**：没有基准正式版本时，候选通过批准后先创建并确认图快照，再以单一激活单元建立首个 Formal MappingRevision 和当前指针。确认完成前 Formal Query 没有新的正式结果。
2. **正常版本前进**：旧正式版本仍是当前版本；新图 Commit 确认后，SQLite 原子激活新 Formal MappingRevision；双侧读回成功后才更新 Proposal、Merge Request Buffer 和来源处置。
3. **候选过期**：另一个操作已经从相同基准建立新正式版本时，旧候选不能继续激活，必须标记 `stale` 并重新生成候选。
4. **图已写入、治理未激活**：新 Commit 作为未激活历史保留，Formal Query 继续使用旧正式版本；恢复时复用原 Commit，不创建重复正式版本。
5. **治理激活结果未知**：FormalizationResult 进入 `reconciliation_required`；查询按双侧校验结果处理，不根据写入调用是否返回成功来推断正式化成功。
6. **正式化成功、通知失败**：正式 MappingRevision 继续可查询，通知单独显示失败并可重试。
7. **普通执行失败**：只产生 Execution Record 或 MCP Submission，不触发跨存储正式化；只有路线、依赖或版本事实发生变化时才创建新的 Proposal。

## 排除范围

本设计不规定 SQL DDL、TerminusDB Schema、ORM、API 参数、消息队列、网络重试库、具体锁实现、跨 TerminusDB/SQLite 原子事务、部署拓扑或通知传输协议。实现必须满足本设计的业务状态、幂等、可见性、查询和审计不变量，但可以选择不同的技术方案。
