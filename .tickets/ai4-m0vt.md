---
id: ai4-m0vt
status: closed
deps: [ai4-ay0e, ai4-r3so]
links: [ai4-e257, ai4-vbnr, ai4-r3so, ai4-xrxw]
created: 2026-10-17T15:21:05Z
type: grilling
priority: 1
assignee: hanjiang
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, execution, product, ai4science]
---
# 首版任务执行、交接与失败恢复模型

明确 SciWeave 首版围绕 Research Mapping 的任务执行语义：任务状态、人员/Personal Agent/Task Agent 分派、MCP Submission、Execution Record、结果提交、TaskNode Owner 审核、重试、转交、人工接管、失败分类和路线改变触发 Mapping Proposal。只确定产品与领域规则，不进入消息队列、模型选择或 API 实现。

## Design

首版采用“TaskNode 负责规划和资格，Execution Record 负责每次运行，MCP Submission 负责受控入口”的三层边界：

- TaskNode 版本描述要完成什么以及正式调度资格；它不记录某一次运行的完整过程。
- Execution Record 描述一次具体执行、重试、转交或人工接管；每次重新运行创建新的 Execution Record，不覆盖旧记录。
- MCP Submission 是人员或 Agent 向平台提交结果、失败报告或路线变化请求的入口；提交不等于结果接纳，也不等于 Mapping 正式变更。
- Central Agent 可以调度、重试、转交和记录，但不能代替 TaskNode Owner 接纳结果，也不能代替 Project Owner 正式发布事实。

## TaskNode 运行投影

TaskNode 的 Mapping 生命周期由 `ai4-r3so` 定义。首版只允许平台根据正式版本和 Execution Record 生成运行投影：

- `not_ready`：正式节点存在，但前置条件或输入未满足；
- `ready`：满足正式调度资格，可以创建 Execution Record；
- `in_progress`：存在活动 Execution Record；
- `awaiting_acceptance`：执行已经产生结果，等待 TaskNode Owner 接纳；
- `accepted`：结果被节点负责人接纳，可作为后续任务输入或正式结果发布候选；
- `blocked`：无法继续执行，但尚未判断为路线变化；
- `route_change_required`：失败或新证据改变研究假设、前置条件或路线，必须提交 Mapping Proposal。

这些状态是运行投影，不覆盖 TaskNode 的候选/正式/废弃版本状态。重试不会创建新的 TaskNode 版本。

## Execution Record 状态和转换

一次 Execution Record 使用最小状态集：

```text
queued → running → succeeded → awaiting_acceptance → accepted
                  ├→ failed
                  ├→ handoff_required → handed_off
                  ├→ human_takeover
                  └→ cancelled

awaiting_acceptance → supplement_requested → awaiting_acceptance
                    ├→ needs_revision → queued
                    └→ rejected
```

规则如下：

- `retry` 不是状态，而是从 `failed`、`needs_revision` 或可重试的 `cancelled` 记录创建新的子 Execution Record，并通过 `retry_of` 关联原记录。
- `supplement_requested` 表示 TaskNode Owner 认为结果缺少数据、说明或证据；提交者可以补充 MCP Submission，补充内容必须关联原 Execution Record。
- `needs_revision` 表示结果本身需要重新执行或修改，通常创建新的 Execution Record；原记录保持不可变。
- `rejected` 表示当前结果未被接纳。被拒绝的结果仍可作为审计证据，不能作为后续任务的正式输入；重新执行必须创建新的 Execution Record。
- `handoff_required` 表示当前执行主体不能继续；转交后创建新的 Execution Record，通过 `handoff_of` 关联原记录，原记录保持不可变。
- `human_takeover` 表示人员接管当前任务；接管前后的操作者、原因和时间必须分别审计。
- `succeeded` 只表示执行过程产生了可提交结果，不表示结果已经被科研负责人接纳。
- `accepted` 只表示 TaskNode Owner 完成第一阶段结果接纳。首版不另设“正式科研结论”对象；结果可以作为后续任务输入或受控资源引用，只有它引起 Formal Mapping 变化时才需要 Project Owner 审核 Proposal。
- 失败记录不可删除或覆盖；更正通过新的 Submission 或新的 Execution Record 表达。

## 执行主体和责任

| 参与者 | 可以做什么 | 不能替代什么 |
| --- | --- | --- |
| 研究人员 | 执行任务、提交结果、判断证据、接管失败任务 | 不能绕过正式审核直接修改 Formal Mapping |
| Personal Agent | 代表研究人员执行被授权的结构化工作、提交结果或失败报告 | 不能自行接纳结果或正式发布 |
| Task Agent | 执行边界明确、可重复的任务并提交结果 | 不能改变任务路线或批准科研事实 |
| TaskNode Owner | 检查结果、证据和完成条件，接纳、要求补充、退回或拒绝结果 | 不能代替 Project Owner 批准 Formal Mapping 路线变更 |
| Central Agent | 检查前置条件、创建调度、重试、转交、记录执行和预审提交 | 不能代替人工科研判断和正式批准 |
| Project Owner | 批准正式 Research Mapping 路线变更 | 首版不直接修改候选正文，也不另建独立的“正式科研结论”对象 |

## MCP Submission 最小关系

每个提交至少记录：

- `submission_id` 和客户端提供的 `idempotency_key`；
- 提交者及 `actor_type`；
- `task_node_logical_id`、`task_node_version_id` 和 `execution_record_id`；
- `base_formal_revision_id`；
- 提交类型：结果、失败报告、接纳请求或路线变更请求；
- 结果摘要、证据引用、失败分类或 Proposal 引用；
- 内容摘要、创建时间和处理结果。

MCP Submission 只能进入受控 Buffer 或 Execution Record。它不能直接写入 Formal Mapping，也不能把一个普通执行状态伪装成 Proposal。

## 重试、转交、人工接管与幂等

- `transient`、`environment` 和可修复的 `input` 失败可以由 Central Agent 重试；重试使用同一 TaskNode 版本，创建新 Execution Record。
- 当前执行主体能力不足、资源不可用或责任人变更时可以转交；转交必须记录原主体、新主体、原因和交接时间。
- 失败需要科研人员观察、判断或补充实物信息时进入人工接管；人工处理结果仍通过 MCP Submission 或人工提交进入审核。
- 同一 `idempotency_key` 加相同内容摘要的重复提交返回第一次处理结果，不创建第二条有效结果；同一幂等键对应不同内容时拒绝并记录冲突。
- 同一 Execution Record 不允许被两个成功结果覆盖。并行执行必须创建不同的 Execution Record，并由 TaskNode Owner 选择或接纳结果。

## 失败分类和路线变化

| 失败类型 | 首版处理 | 是否创建 Mapping Proposal |
| --- | --- | --- |
| 临时服务、网络或模型失败 | 重试 | 否 |
| 执行主体能力不足或资源不可用 | 转交或人工接管 | 否，除非路线发生变化 |
| 输入缺失但任务目标不变 | 补充输入后重试 | 否 |
| 结果不满足完成条件但路线不变 | 退回、重试或转交 | 否 |
| 研究假设、前置条件、依赖语义或路线发生变化 | 提交结构化 ChangeSet，进入 Proposal | 是 |

普通失败只改变执行记录和运行投影，不自动改变 Formal Mapping。只有最后一类变化可以生成 Proposal；Proposal 的生命周期和正式化规则由 `ai4-xrxw` 定义。

## 两阶段审核边界

1. Execution Record 进入 `awaiting_acceptance` 后，由 TaskNode Owner 检查完成条件、结果摘要、证据引用和失败说明，可以接受、要求补充、要求重做或拒绝。
2. 补充材料通过新的 MCP Submission 关联原 Execution Record；重新执行通过新的 Execution Record 关联 `retry_of` 或 `revision_of`。
3. 被接纳的结果可以作为后续任务的输入或受控资源引用，但首版不单独创建“正式科研结论”对象。
4. 改变 Formal Mapping、恢复/废弃路线或改变依赖语义，必须进入 Mapping Proposal，并由 Project Owner 进行 Formal Publication Review。
5. 每一步都追加 AuditEvent，至少关联操作者、Execution Record、MCP Submission、TaskNode 版本和结果。

## Acceptance Criteria

- [x] 形成任务和执行记录的状态清单与转换规则，并明确重试不是覆盖旧记录。
- [x] 明确人员、Personal Agent、Task Agent、TaskNode Owner、Central Agent 和 Project Owner 的责任边界。
- [x] 明确 MCP Submission 与 Execution Record 的最小关系、幂等键和提交不等于批准的规则。
- [x] 明确重试、转交、人工接管、重复提交和并行执行的最小语义。
- [x] 明确 TaskNode Owner 结果接纳与 Project Owner 正式批准的边界。
- [x] 明确普通失败与必须生成 Mapping Proposal 的路线变化型失败。
- [x] 不引入消息队列、模型选择或 API 实现。

## Answer

SciWeave 首版把“任务定义”“一次执行”“受控提交”和“正式治理”分开。这样普通执行失败可以在不改变 Formal Mapping 的前提下恢复；只有研究路线真正变化时才创建 Proposal，并保留完整执行与审计链。

## Notes

**2026-10-18T08:28:55Z**

已完成首版任务执行模型：明确 TaskNode 运行投影、Execution Record 状态转换、MCP Submission 最小关系、重试/转交/人工接管/幂等语义、失败分类和 TaskNode Owner 与 Project Owner 的两阶段审核边界。普通失败不改变 Formal Mapping，路线变化才创建 Proposal。验收标准全部满足。
