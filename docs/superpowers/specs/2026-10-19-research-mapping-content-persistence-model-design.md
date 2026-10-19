# Research Mapping 内容持久化模型设计

- 日期：2026-10-19
- 关联工单：[`ai4-t5zl`](../../../.tickets/ai4-t5zl.md)
- 状态：施工前领域规格已收敛

## 目的与边界

本设计把已确定的 Research Mapping 产品字段落实为可持久化的领域对象：TaskNode、DependencyEdge、对象版本和 Formal MappingRevision。字段是领域规格，不规定 TerminusDB Schema 写法、DDL、ORM、API 或序列化格式。

Research Mapping 图存储保存 TaskNode/DependencyEdge 的不可变版本内容、精确版本引用和候选/正式快照所需的图关系。任务运行状态、执行日志、失败详情和结果正文不写入图对象；它们分别由 Execution Record、MCP Submission 和 Resource/ResourceVersion 体系管理。Proposal、candidate branch、candidate Commit、Formal MappingRevision 的审核事实和审计索引由 Research Mapping 治理记录管理，具体结构见 [`ai4-mjku`](../../../.tickets/ai4-mjku.md)。

一个 `Formal MappingRevision` 是产品层的正式版本身份，不等同于 TerminusDB Commit：TerminusDB Commit 只标识图存储快照；只有精确图 Commit 已读回确认，且 SQLite 正式版本记录、当前指针和成功 FormalizationResult 在本地激活单元中共同生效后，该版本才可进入正式查询和正式调度。跨存储正式化及失败恢复的完整规则见 [`Research Mapping 跨存储正式化一致性与失败恢复设计`](./2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md)。

## 通用标识和字段规则

- `mapping_domain_id`：Research Mapping 治理上下文的稳定标识。若一个项目只有一张逻辑 Research Mapping，仍保留该字段以避免把存储连接名当作业务身份。
- `logical_id`：TaskNode 或 DependencyEdge 的长期逻辑身份。修订、废弃和恢复不改变它。
- `version_id`：某个逻辑对象的一次不可变版本身份，在 `mapping_domain_id` 内唯一且不可复用。
- `formal_revision_id`：产品层 Formal MappingRevision 的不可变身份。
- `proposal_id`、`source_submission_id`、`execution_record_id`：治理或运行记录的稳定关联 ID；它们不是图对象正文。
- 所有 ID、时间、版本引用和状态字段均由平台生成或校验；显示标题不能作为关系键。
- 内容字段创建后不可原地修改。任何目标、完成条件、输入输出、责任主体、依赖语义或激活条件的变化，都创建新的 `version_id`。

## TaskNode 持久化字段

TaskNode 是 Research Mapping 唯一的拓扑节点。它只表达任务定义及其治理版本，不保存前置列表；前置和后继关系全部由 DependencyEdge 表达。

| 字段 | 必填性 | 语义和约束 | 归属 |
| --- | --- | --- | --- |
| `mapping_domain_id` | 必填 | 所属 Research Mapping 上下文，创建后不变 | 图对象/治理关联 |
| `logical_id` | 必填 | 稳定任务身份；同一领域内不可复用 | 图对象 |
| `version_id` | 必填 | 不可变任务版本；同一领域内唯一 | 图对象 |
| `title` | 必填 | 面向研究人员的短标题，不承担关系语义 | 图对象 |
| `objective` | 必填 | 任务要解决的问题或目标；不得用学科专属类型替代目标描述 | 图对象 |
| `scope` | 必填 | 任务边界、排除项和必要上下文 | 图对象 |
| `acceptance_criteria` | 必填 | 可判定的完成/接纳条件列表；至少有一条可检查条件 | 图对象 |
| `expected_outputs` | 必填 | 预期输出的结构化描述和可验证要求；不内嵌输出正文 | 图对象 |
| `input_refs` | 可选 | 精确输入版本引用及其是否必需；只能引用稳定的 ResourceVersion/WikiRevision 等版本 ID，并以弱引用表达跨域关系 | 图对象 |
| `required_evidence` | 必填 | 结果接纳需要的证据类型、完整性要求和判断点；不保存证据载体 | 图对象 |
| `resource_refs` | 可选 | 与任务有关的已知资源/证据版本引用和角色；不得只写可变的“最新资源” | 图对象 |
| `task_owner_id` | 必填 | 负责第一阶段结果接纳和任务相关变更审核的 TaskNode Owner | 图对象 |
| `executor_refs` | 可选 | 人员、Personal Agent、Task Agent 或协作集合的稳定身份引用；计划阶段可为空，正式调度前必须能解析到经授权执行主体 | 图对象 |
| `human_decision_points` | 可选 | 需要研究人员判断的事项、触发时机和所需输入；不保存判断结果 | 图对象 |
| `lifecycle_state` | 必填 | 版本治理状态：`candidate`、`formal`、`superseded`、`rejected`、`invalidated` | 图对象的受控投影 |
| `proposal_id` | 候选必填，正式可为空 | 候选版本所属 Mapping Proposal；正式版本的来源 Proposal 由 Formal MappingRevision 记录 | 治理关联 |
| `base_formal_revision_id` | 候选必填，初始版本可为空 | 候选创建所依据的精确 Formal MappingRevision；不允许只写“当前版本” | 治理关联 |
| `formal_revision_id` | 正式必填，候选为空 | 该版本进入正式查询的 Formal MappingRevision；必须与当前正式快照一致 | 治理关联 |
| `derived_from_version_id` | 修订时必填 | 同一 `logical_id` 的直接来源版本；首个版本为空 | 图对象 |
| `supersedes_version_id` | 替代时必填 | 被当前版本替代的同逻辑对象版本；必须与 `derived_from_version_id` 一致或形成可解释的版本链 | 图对象 |
| `restores_version_id` | 恢复时必填 | 恢复已废弃/失效语义时指向被恢复的历史版本；恢复仍创建新版本 | 图对象 |
| `created_by`、`created_at` | 必填 | 创建主体和创建时间；审计更正不覆盖原值 | 图对象/审计关联 |
| `source_submission_id` | 初始来源可选 | 产生该版本的 Mapping Buffer Submission；仅作治理关联 | 治理关联 |

### TaskNode 约束

1. `lifecycle_state = candidate` 时，必须有 `proposal_id` 和 `base_formal_revision_id`，不得有 `formal_revision_id`，且只能出现在对应 candidate branch 的候选快照中。
2. `lifecycle_state = formal` 时，必须有 `formal_revision_id`；该版本必须属于该 Formal MappingRevision 的图快照。正式版本一经创建，其内容和版本身份不变。
3. `superseded`、`rejected`、`invalidated` 版本仍保留以供审计，但不得被 Formal Query 或正式调度选取。
4. `acceptance_criteria`、`expected_outputs`、`required_evidence` 是任务定义，不是 Execution Record 的结果；执行结果、重试、转交和人工接管不更新这些字段。
5. `input_refs` 和 `resource_refs` 只保存精确版本引用。跨 LLM-Wiki 的引用是带领域语义的弱引用，不建立本地强外键，也不自动跳转到目标对象的最新版本。
6. 每个正式可调度 TaskNode 至少有一个可解析的 `task_owner_id`；自动执行还必须有有效的 `executor_refs` 或明确的人工接管路径。

## DependencyEdge 持久化字段

DependencyEdge 是有方向的拓扑关系。方向固定为“前置任务 → 依赖该任务的任务”，即 `source_node_version_ref` 是前置节点，`target_node_version_ref` 是等待或使用其结果的节点。

| 字段 | 必填性 | 语义和约束 | 归属 |
| --- | --- | --- | --- |
| `mapping_domain_id` | 必填 | 所属 Research Mapping 上下文 | 图对象/治理关联 |
| `logical_id` | 必填 | 稳定依赖关系身份；不把一对节点直接当作边身份 | 图对象 |
| `version_id` | 必填 | 不可变边版本；同一领域内唯一 | 图对象 |
| `source_node_version_ref` | 必填 | 精确的前置 TaskNode `logical_id + version_id` | 图对象关系 |
| `target_node_version_ref` | 必填 | 精确的后继 TaskNode `logical_id + version_id` | 图对象关系 |
| `dependency_kind` | 必填 | `information`、`blocking`、`conditional` 或 `alternative` | 图对象 |
| `required_outputs` | 按关系必填 | 目标任务需要源任务提供的输出标识和完整性要求；`blocking` 至少一项 | 图对象 |
| `activation_condition` | 条件/替代必填 | 结构化激活条件；无条件关系必须显式表示为无条件，而不是缺省猜测 | 图对象 |
| `alternative_group_id` | `alternative` 必填 | 将多个互斥/可替代前置边归入同一组；其他关系为空 | 图对象 |
| `blocks_until` | `blocking` 必填，其他可选 | 目标何时解除阻塞，例如输出可用、证据接纳或人工批准 | 图对象 |
| `route_change_trigger` | 可选 | 失败或新证据何时只需恢复、何时必须建议 Mapping Proposal；不会自动改图 | 图对象 |
| `lifecycle_state` | 必填 | 与 TaskNode 相同的版本治理状态词汇 | 图对象的受控投影 |
| `proposal_id` | 候选必填，正式可为空 | 候选边所属 Proposal | 治理关联 |
| `base_formal_revision_id` | 候选必填，初始边可为空 | 候选创建的正式基准 | 治理关联 |
| `formal_revision_id` | 正式必填，候选为空 | 边进入正式查询的正式版本 | 治理关联 |
| `derived_from_version_id`、`supersedes_version_id` | 修订/替代时必填 | 追踪依赖语义的版本演化 | 图对象 |
| `created_by`、`created_at` | 必填 | 创建主体和时间 | 图对象/审计关联 |
| `source_submission_id` | 来源明确时可选 | 产生该边版本的提交关联 | 治理关联 |

### DependencyEdge 约束

1. 两个端点必须存在于同一 `mapping_domain_id`，且精确指向 TaskNode 版本；禁止指向只有 `logical_id` 没有 `version_id` 的“当前节点”。
2. 禁止自环。正式调度所使用的 `blocking` 子图必须无环；任何会形成无法满足的阻塞环的候选都不能通过 Central Agent 预审。
3. `alternative` 边必须有 `alternative_group_id` 和可判定的 `activation_condition`；平台不得让 Agent 根据自然语言自行选择替代路线。
4. 节点版本发生变化时，所有引用旧版本的相关边必须在候选 ChangeSet 中重新确认或创建新边版本；不能静默把旧边改指新节点。
5. 同一 `logical_id` 的边版本不能原地改变方向、关系类型、输出要求、阻塞条件或路线触发条件。废弃关系创建新版本并保留历史。
6. DependencyEdge 不保存执行日志、错误详情、资源正文或完整结果摘要；这些信息分别进入 Execution Record、Resource Reference 和结果资源版本。

## Formal MappingRevision 与存储归属

`Formal MappingRevision` 是“产品层正式快照身份 + 图存储精确 Commit + 治理批准事实”的组合引用。为了避免两侧记录漂移，字段归属如下：

| 对象/字段 | 主要持有方 | 规则 |
| --- | --- | --- |
| TaskNode、DependencyEdge 版本正文和端点关系 | Research Mapping Store（TerminusDB） | 候选/正式内容不可变；候选与正式快照由 Commit 区分 |
| `formal_revision_id`、`base_formal_revision_id` | Mapping 治理记录 | 产品层稳定版本身份；不能用 Commit hash 代替 |
| `terminus_store_id`、`formal_branch_id`、`formal_commit_hash` | Mapping 治理记录，同时可被存储审计索引引用 | 精确指向一次图快照；Commit 不表示批准 |
| `source_proposal_id`、`approval_audit_event_id`、`published_by`、`published_at` | Mapping 治理记录 | 证明该正式版本由哪个候选和哪个 Project Owner 审核产生 |
| 当前正式版本指针 `current_formal_revision_id` | Mapping 治理记录 | 一个 `mapping_domain_id` 同时只有一个当前指针；仅在 TerminusDB 精确 Commit 已确认后，通过 SQLite 本地激活单元按 `ai4-azx2` 的一致性规则更新 |

一个 Formal MappingRevision 至少包含以下逻辑字段：

- `formal_revision_id`、`mapping_domain_id`；
- `terminus_store_id`、`formal_branch_id`、`formal_commit_hash`；
- `base_formal_revision_id`（首个正式版本为空）；
- `source_proposal_id`、`approval_audit_event_id`；
- `published_by`、`published_at`；
- 可选的图快照摘要、节点/边数量和影响分析引用。摘要只用于校验和审计，不替代图正文。

正式版本记录不可原地修改。新正式版本通过 `base_formal_revision_id` 形成链；旧正式版本继续可审计，但只有当前 `current_formal_revision_id` 进入普通 Formal Query 和正式调度。

## 查询和调度边界

- **普通查询 / Formal Query**：只读取当前 Formal MappingRevision 中 `lifecycle_state = formal`、属于该版本且未被废弃/失效的 TaskNode 和 DependencyEdge。
- **Proposal Preview**：必须显式提供 `proposal_id`，读取该 Proposal 的候选快照，并显示 `base_formal_revision_id` 和候选状态；不得混入其他 Proposal 内容。
- **正式调度**：只读取当前正式版本；所有相关边必须属于同一正式快照，`blocking` 前置条件已满足，输入/证据引用可用，且没有待处理人工判断点。
- **运行投影**：`ready`、`in_progress`、`blocked`、`awaiting_acceptance`、`route_change_required` 等状态来自正式图和 Execution Record 的计算，不覆盖图对象的 `lifecycle_state`。

## 场景一致性检查

1. **首次创建**：创建新的 TaskNode `logical_id/version_id` 和必要的 DependencyEdge；没有来源版本。进入候选前，节点/边不出现在 Formal Query；经批准后分别关联新的 Formal MappingRevision。
2. **修改任务目标**：保留旧版本，创建同一 `logical_id` 的新 `version_id`，记录 `derived_from_version_id` 和 `supersedes_version_id`。候选期间旧正式版本继续用于正式查询，直到新 Proposal 正式化。
3. **新增评估步骤**：新增 T4 和新的边版本；如果改变正式路线或依赖，必须从当前 Formal MappingRevision 创建 Proposal，不能直接写 formal branch。
4. **普通执行失败**：只新增 Execution Record 或 MCP Submission，TaskNode/DependencyEdge 版本不变；只有研究目标、前置条件、依赖语义或路线触发条件变化时才创建 Proposal。
5. **候选驳回**：候选节点、边、Commit、Diff 和审核事件保留为只读审计事实；Formal Query 和正式调度继续读取原 Formal MappingRevision。
6. **跨场景替换**：将 Iris 替换为 NOAA 时只替换任务内容、资源版本、执行者和验收脚本；TaskNode、DependencyEdge、版本和治理字段不增加学科专属对象。

## 排除范围

本设计不定义 TerminusDB Schema/DDL、SQLite 表结构、API 参数、消息队列、冲突算法、权限实现或跨 TerminusDB 原子事务。跨存储正式化的业务状态、提交确认、失败可见性、幂等重试、补偿和查询权威见 [`Research Mapping 跨存储正式化一致性与失败恢复设计`](./2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md)；本设计仅提供稳定字段和引用。
