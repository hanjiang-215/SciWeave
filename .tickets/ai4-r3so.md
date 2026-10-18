---
id: ai4-r3so
status: closed
deps: [ai4-ebqx, ai4-u3rs]
links: [ai4-m0vt, ai4-xrxw, ai4-xup8]
created: 2026-10-16T13:42:18Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, domain-model, ai4science]
---
# Research Mapping 节点与依赖边字段模型

细化统一 Research Mapping 中 TaskNode 与 DependencyEdge 的领域字段、必填条件、字段语义、状态约束和对象间关系。只确定产品/领域模型，不进入数据库列、API 参数或代码结构。字段模型为执行模型和 Proposal 治理提供稳定引用，但不替代对应工单决定状态转换和审计规则。

## Design

首版采用“不可变版本对象 + 受控治理状态 + 外部执行记录”的最小模型：

- `logical_id` 标识一个长期稳定的逻辑任务或逻辑依赖；`version_id` 标识该对象的一次不可变版本。
- 版本内容创建后不能原地修改。修改、废弃、恢复和路线调整都创建新的节点或边版本，并通过 `derived_from`、`supersedes` 或 `restores` 追踪来源。
- 候选版本必须记录 `base_formal_revision_id` 和 `proposal_id`；正式版本必须记录 `formal_revision_id`。TerminusDB Commit 只表示存储变化，不表示产品层已经批准。
- TaskNode 保存任务自身信息；依赖、阻塞和激活语义全部由 DependencyEdge 保存。节点不重复保存前置节点列表或后继节点列表。
- Execution Record、MCP Submission、AuditEvent 和 Proposal 通过稳定的逻辑 ID、版本 ID 和关联 ID 引用 Mapping 对象，但不嵌入节点或边正文。

## TaskNode 最小字段

| 字段组 | 字段 | 必填性与规则 |
| --- | --- | --- |
| 身份 | `logical_id`、`version_id` | 必填；逻辑身份稳定，版本身份不可复用 |
| 来源 | `derived_from`、`supersedes`、`base_formal_revision_id` | 候选或修订时必填；初始节点可没有来源 |
| 目标 | `title`、`objective`、`scope` | `title` 和 `objective` 必填；描述任务要解决什么问题及边界 |
| 完成条件 | `acceptance_criteria`、`expected_outputs` | 必填；必须能判断任务是否达到结果接纳条件 |
| 输入与证据 | `input_refs`、`required_evidence`、`resource_refs` | 输入和要求按引用表达；不把资源正文写入节点 |
| 责任 | `task_owner_id`、`executor_refs`、`human_decision_points` | `task_owner_id` 必填；执行者可为人员、Personal Agent、Task Agent 或协作集合；人工判断点可选 |
| 治理 | `lifecycle_state`、`proposal_id`、`formal_revision_id` | 候选版本必须关联 Proposal；正式版本必须关联 Formal MappingRevision |
| 元数据 | `created_by`、`created_at`、`source_submission_id` | 必填或在首版由平台补齐，用于责任追踪 |

`lifecycle_state` 只表达 Mapping 对象的治理生命周期：`candidate`、`formal`、`superseded`、`rejected`、`invalidated`。任务运行中的 `ready`、`running`、`blocked`、`awaiting_acceptance` 等状态属于运行投影或 Execution Record，不得覆盖 Mapping 版本状态。

## DependencyEdge 最小字段

| 字段组 | 字段 | 必填性与规则 |
| --- | --- | --- |
| 身份 | `logical_id`、`version_id` | 必填；边也有独立逻辑身份和不可变版本 |
| 方向 | `source_node_version_ref`、`target_node_version_ref` | 必填；方向为“前置任务 → 依赖该任务的任务” |
| 关系 | `dependency_kind` | 必填；首版至少区分 `information`、`blocking`、`conditional` 和 `alternative` |
| 条件 | `required_outputs`、`activation_condition` | 依赖任务需要的输出和激活条件；没有条件时显式表示无条件 |
| 执行语义 | `blocks_until`、`route_change_trigger` | 说明何时阻塞目标任务，以及失败何时只需重试、何时提示路线变更 |
| 来源与治理 | `derived_from`、`proposal_id`、`lifecycle_state`、`formal_revision_id` | 遵循与 TaskNode 相同的候选/正式边界 |
| 元数据 | `created_by`、`created_at`、`source_submission_id` | 用于提交和审计追踪 |

### DependencyEdge 的调度规则

- `information`：表示目标任务需要源任务产出的信息；只有在 `required_outputs` 被标记为必需时才阻塞，否则可以先执行并在结果中声明缺失信息。
- `blocking`：目标任务必须等待源任务满足 `blocks_until`，否则保持 `not_ready` 或 `blocked`。
- `conditional`：由 `activation_condition` 判断是否激活；条件无法判断时不得自动调度，转为人工判断或补充信息。
- `alternative`：表示多个候选前置路线中的替代关系；首版采用“任一满足明确条件的路线即可继续”，条件必须在边上写明，不能由 Agent 自行猜测。
- `route_change_trigger` 只表示失败或证据何时需要建议路线变化，不会自动修改 Formal Mapping；确认路线变化后必须创建 Mapping Proposal。

DependencyEdge 不保存执行日志、错误详情、资源正文或完整结果摘要。错误和运行结果进入 Execution Record，资源通过 Resource Reference 关联，路线变化通过 Proposal 的 ChangeSet 表达。

## 版本和状态约束

1. 节点或边的内容不可原地修改；任何改变目标、完成条件、输入输出、依赖关系、阻塞语义或路线激活条件的操作都必须产生新版本。
2. 候选节点和边只能写入对应 Proposal 的 candidate branch；候选 Commit 不得被普通查询或正式调度读取。
3. Formal Query 只读取当前 Formal MappingRevision 中状态为 `formal` 且未被替代、废弃或失效的节点和边。
4. 正式分支只能由 Project Owner 完成 Formal Publication Review 后，在平台受控推进；rebase 或其他 TerminusDB 存储操作不能单独改变产品批准状态。
5. 节点版本发生变化时，引用它的依赖边必须在候选 ChangeSet 中重新确认或创建新边版本，不能继续静默引用过期版本。
6. 失败、重试和执行状态不会自动修改 Mapping；只有研究目标、前置条件、依赖语义或路线发生变化时，才必须创建 Mapping Proposal。

## 关联键和查询边界

- `Execution Record` 至少关联 `task_node_logical_id`、`task_node_version_id`、`execution_record_id` 和产生它的 `MCP Submission`。
- `MCP Submission` 至少携带提交者、提交幂等键、目标节点/边版本、`base_formal_revision_id`、内容摘要和提交时间。
- `AuditEvent` 至少关联操作者、操作对象、对象版本、基准 Formal MappingRevision、Proposal 或 Execution Record，以及操作结果。
- 普通 Mapping 查询和正式调度只读取当前 Formal MappingRevision；候选预览必须明确带有 `proposal_id`，并标记为候选内容。
- 正式调度资格至少要求：节点和所有相关边属于当前 Formal MappingRevision；节点未被废弃或失效；所有 `blocking` 前置边满足；所需输入和证据已被正式接纳；没有待处理人工判断点。

## 场景中立边界

字段只描述任务目标、依赖、输入输出、证据、责任和治理，不引入生物、材料、健康或其他学科的固定对象。具体科研场景只能替换初始节点、边、资源引用、执行者和验收脚本。

## Acceptance Criteria

- [x] 形成 TaskNode 与 DependencyEdge 的字段清单和字段语义，标明稳定身份、版本、必填/可选、可变性和来源。
- [x] 明确 TaskNode 的目标、范围、输入、输出、完成条件、负责人、执行主体、人工判断点、资源引用和前置条件的最小表达。
- [x] 明确 DependencyEdge 的方向、关系类型、前置条件、阻塞语义、条件/分支语义和版本引用规则；不把执行日志或资源正文塞入边。
- [x] 明确节点与边的状态约束、候选/正式版本边界，以及创建、替代、废弃和路线变化的表达；不把 TerminusDB Commit 直接当作产品批准状态。
- [x] 为 Execution Record、MCP Submission、AuditEvent 和 Mapping Proposal 提供稳定的最小关联键与版本引用，并把具体状态转换交由对应工单确定。
- [x] 覆盖任务规划、执行、资源引用、失败与路线演化的最小表达，包括重复执行、重试/转交/人工接管和结果接纳后的引用位置。
- [x] 明确普通查询、Formal Query 和正式调度所需的资格字段及过滤边界，确保候选版本不会进入正式视图。
- [x] 明确节点和边在跨场景示例替换时保持场景中立，不进入数据库列、API 参数或代码结构。

## Answer

Research Mapping 首版使用上述最小字段和约束。该模型把“任务是什么”与“任务运行过什么”分开，把“候选版本是什么”与“是否已经成为正式事实”分开，为 `ai4-m0vt` 的执行记录和 `ai4-xrxw` 的 Proposal 生命周期提供稳定引用，不扩展到数据库实现。

## Notes

**2026-10-18T08:28:55Z**

已完成首版 TaskNode 与 DependencyEdge 最小字段模型：明确稳定身份、不可变版本、责任主体、输入输出、依赖/阻塞语义、候选与正式边界、正式查询与调度资格，并建立与 Execution Record、MCP Submission、AuditEvent、Proposal 的关联键。验收标准全部满足。
