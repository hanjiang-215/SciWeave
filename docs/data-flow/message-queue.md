# 消息队列：正式版本到下游执行

本文描述 Research Mapping 正式版本发布后，如何通过消息队列通知下游、等待下游配置、选择 Workflow Agent 并触发一次执行。它只描述消息协作边界，不实现 Redpanda 客户端、邮件服务或领域管理 MCP。文中所称“交接协调服务”目前是待决策的角色，其职责、存储边界和部署形态由[交接协调服务的职责、存储边界与 centre-control 部署形态](../../.tickets/ai4-p5f3.md)收敛；在该票关闭前，下文的服务名和部署位置均是设计约束，不代表已存在的代码项目。

## 参与者与事实归属

消息链路涉及三类事实。每类事实只有一个权威来源：

```text
Research Mapping
    TaskNode、DependencyEdge、正式版本、task_owner_id、executor_refs

Registry
    Principal、Workflow Agent、Agent instance 的身份和基本登记信息

Redpanda / 消息服务
    事件排队、消费者 offset、投递和消费过程

交接协调服务
    PendingHandoff、HandoffDispatch 和重算/派发状态
```

`TaskNode.executor_refs` 直接引用稳定的 Workflow Agent `agent_id`。它是正式任务分配和自动执行路由的权威来源。

Registry 不保存 `task_node_id` 集合，也不保存“某个 Agent 负责哪些节点”的第二份事实。Registry 中登记了某个 Agent，不代表它获得任何 TaskNode 的执行权限；消息服务只能依据正式 Map 的 `executor_refs` 判断执行关系。

一个 Workflow 可以是单个 Agent，也可以包含 Router、Orchestrator、Parallel 或 Agents as Tools 等多个内部 Agent。平台只为这个 Workflow 注册一个逻辑 `agent_id`，内部 Agent 不单独成为消息消费者、Worker Lease 目标或平台级 ExecutionRecord。

## 交接协调服务的暂定边界

当前设计需要一个位于中央服务侧的交接协调角色，但仓库现有的 `centre-agents` 是执行候选预审的 Centre Agent，`research-map` 是 Research Mapping 领域服务，二者都不应默认承担通用交接协调职责。

该角色的暂定职责是：

- 消费 `downstream_dependency_notice`；
- 查询当前正式 Mapping，而不是复制 TaskNode/DependencyEdge 正文；
- 判断正式节点、正式边、版本引用、所需输出和激活条件；
- 创建或更新 `PendingHandoff`；
- 条件满足时生成 `task_handoff_ready`；
- 没有可用自动执行主体时生成 `human_notification_intent` 或通知意图。

它不负责修改正式 Mapping、授予执行权限、启动 Worker、执行 Centre Agent 预审或把邮件发送成功解释成任务完成。是否在 `sci-weave/centre-control/handoff-coordinator/` 形成独立 Python 子项目，以及 `PendingHandoff` 的权威存储归属，仍由上述决策票裁定。

## 物理 topic 与逻辑频道

消息交接按接收目标和处理语义分成四个固定物理 topic：

```text
sciweave.dependency-notice
    → downstream_dependency_notice
    → 交接协调服务

sciweave.task-handoff.<agent_id>
    → task-workflow 的 Task Agent subscriber

sciweave.governance-events
    → candidate_created、candidate_head_updated、formal_revision_published
    → centre-workflow 的可扩展订阅者

sciweave.notification-intent
    → human_notification_intent
    → email-service 或其他人工通知投递服务
```

业务上每个目标 TaskNode 仍拥有独立逻辑频道；物理 topic 不按 TaskNode 或每个 Workflow 动态创建。任务交接消息以目标 TaskNode 逻辑 ID或目标版本引用作为路由键和分区键。Centre Workflow 通过独立订阅声明和消费者组扩展；邮件服务只消费通知意图。topic 订阅不构成授权来源，正式 `executor_refs` 仍是 TaskNode 执行关系权威。

三类接收目标可以共享统一消息封套，但不得把它们都伪装成 `task_handoff_ready`：`task-workflow` 才能创建 Task Agent 的 `ExecutionRecord`；`centre-workflow` 触发预审或其他中央 Workflow；`email-service` 只投递人工通知。

详细的目标类型、可扩展订阅和启动恢复流程见 [`message-delivery-recovery.md`](message-delivery-recovery.md)。

## 两层消息语义

上游正式版本发布后，消息系统区分“通知下游”和“允许执行”两层语义。

### 下游依赖通知

`downstream_dependency_notice` 表示：

> 上游已经产生新的正式事实，相关下游需要知道这次变化。

它不会启动 Worker。它可以用于：

- 通知下游负责人；
- 记录等待中的交接；
- 等待目标 TaskNode 正式化；
- 等待其他前置节点完成；
- 等待激活条件变为可判断或满足；
- 等待负责人创建并登记 Workflow Agent。

### 可执行交接

`task_handoff_ready` 表示：

> 目标 TaskNode 和依赖边都属于正式 Map，所需输出和激活条件已经满足，且存在正式配置的执行主体，可以开始一轮执行。

只有 `task_handoff_ready` 才能进入 Task Agent 的消费者组并创建 ExecutionRecord。

```text
formal_revision_published
    → downstream_dependency_notice
    → 交接协调服务
    → 检查正式目标、依赖输出和激活条件
    → task_handoff_ready
    → 目标 Task Agent subscriber
    → ExecutionRecord
    → Worker
```

`downstream_dependency_notice` 的主消费者是交接协调服务，而不是 Centre Agent 或邮件服务。Centre Agent 可以通过独立消费者组旁路观察治理事件，但不负责全局依赖重算；邮件服务只消费人工通知意图，不负责判断是否可以执行。

## 严格的版本约束

正式 `DependencyEdge` 必须精确引用 `source_node_version_ref` 和 `target_node_version_ref`。正式调度只能读取当前正式 MappingRevision 中的正式节点和正式边。

因此，下面三个条件不能同时成立：

```text
上游已经完成正式交接
正式 DependencyEdge 已经存在
下游 TaskNode 还没有正式版本
```

如果下游 TaskNode 或依赖边仍是 candidate，它们不能用于生成正式的 `task_handoff_ready`。此时只能通知负责人继续完成候选提交和正式化，不能假装已经存在一条正式交接边。

如果产品需要在下游正式化之前保存“未来可能的交接”，该事实只能是等待配置记录，不能是正式执行交接。它可以引用目标的 `logical_id`，但不能填写尚未存在的 `target_node_version_ref`。

## 具体场景：文献检索到实验数据分析

### 初始状态

任务 A 是“文献检索”，已经进入正式 Map：

```text
TaskNode A
    logical_id = task:literature-review
    version_id = task-version:1
    task_owner_id = person:alice
    executor_refs = [agent:literature-workflow]
    lifecycle_state = formal
```

任务 B 是“实验数据分析”，目前只有候选版本：

```text
TaskNode B
    logical_id = task:data-analysis
    version_id = task-version:1
    task_owner_id = person:bob
    executor_refs = [agent:data-analysis-workflow]
    lifecycle_state = candidate
```

A 到 B 的依赖边也是 candidate：

```text
DependencyEdge
    logical_id = edge:literature-to-analysis
    source = task:literature-review@task-version:1
    target = task:data-analysis@task-version:1
    dependency_kind = blocking
    required_outputs = [resource:literature-summary]
    lifecycle_state = candidate
```

此时 A 可以执行，B 不能被正式调度。

### A 产生正式输出

A 的 Workflow Agent 执行后，把结果写入草稿箱。结果经过 TaskNode Owner 的一审、候选流程和 Project Owner 的正式发布后，得到正式输出：

```text
resource:literature-summary
resource_version_id = resource-version:55
formal_revision_id = formal-revision:11
```

领域服务发布 `formal_revision_published`，消息中引用 `formal_revision_id` 和正式输出版本。

交接服务检查正式 Map，发现 A 到 B 的边仍然是 candidate，因此：

```text
不发布 task_handoff_ready
创建等待配置事实
通知 Bob
```

等待事实可以表达为：

```json
{
  "pending_handoff_id": "pending:handoff-1",
  "source_node_version_ref": {
    "logical_id": "task:literature-review",
    "version_id": "task-version:1"
  },
  "target_task_node_logical_id": "task:data-analysis",
  "reason": "target_task_not_formal",
  "status": "waiting_for_mapping_formalization"
}
```

此时通知 Bob 的邮件只表示：

```text
上游已经产生正式结果，但下游任务尚未进入正式 Map。
请继续完成下游任务及依赖边的候选提交和正式化。
```

它不表示 B 已经可以执行。

### B 正式化并重新检查

Bob 完成候选提交，经过审核和正式发布后，B 和依赖边进入新的 Formal MappingRevision：

```text
TaskNode B
    logical_id = task:data-analysis
    version_id = task-version:2
    lifecycle_state = formal
    formal_revision_id = formal-revision:12
    executor_refs = [agent:data-analysis-workflow]

DependencyEdge
    logical_id = edge:literature-to-analysis
    version_id = edge-version:2
    source = task:literature-review@task-version:1
    target = task:data-analysis@task-version:2
    dependency_kind = blocking
    required_outputs = [resource:literature-summary]
    blocks_until = output_available
    lifecycle_state = formal
```

交接服务重新检查等待事实：

```text
目标节点已正式化
依赖边已正式化
resource-version:55 已存在
blocking 条件满足
```

同时查询 Registry：

```text
agent:data-analysis-workflow 已登记
```

于是发布：

```text
task_handoff_ready
```

载荷至少包含：

```json
{
  "event_type": "task_handoff_ready",
  "mapping_domain_id": "mapping:project-1",
  "formal_revision_id": "formal-revision:12",
  "business_key": "handoff:edge-version-2:formal-revision-12",
  "source_node_version_ref": {
    "logical_id": "task:literature-review",
    "version_id": "task-version:1"
  },
  "target_node_version_ref": {
    "logical_id": "task:data-analysis",
    "version_id": "task-version:2"
  },
  "dependency_edge_version_ref": {
    "logical_id": "edge:literature-to-analysis",
    "version_id": "edge-version:2"
  },
  "required_outputs": [
    {
      "output_id": "resource:literature-summary",
      "resource_version_id": "resource-version:55"
    }
  ],
  "target_agent_id": "agent:data-analysis-workflow"
}
```

随后：

```text
sciweave.task-handoff
    → target TaskNode + target agent_id 的消费范围
    → gateway/subscriber
    → queued ExecutionRecord
    → Worker Lease
    → Worker 执行一轮 Workflow
```

首版不为每个 TaskNode 动态创建物理 Redpanda topic。任务交接使用按 `agent_id` 隔离的 topic 模板 `sciweave.task-handoff.<agent_id>`；一个 Agent 可负责多个 TaskNode，同一 Agent 的多个实例共享对应消费者组并竞争消费。业务上每个目标 TaskNode 仍拥有独立逻辑频道，消息以目标 TaskNode 逻辑 ID或目标版本引用作为路由和分区键。

## 没有可用 Workflow Agent

如果目标 TaskNode 已正式化、依赖也满足，但：

- `executor_refs` 为空；
- 只配置了人工处理；
- `executor_refs` 指向未登记的 `agent_id`；或
- 目标 Agent 已注销或没有可用运行实例；

则不发布 `task_handoff_ready`。交接协调服务生成：

```text
human_notification_intent
```

邮件服务根据 `task_owner_id` 查询通知联系人并发送邮件。邮件说明：

```text
上游结果已就绪，下游任务已正式化，但目前没有可用的自动执行 Workflow。
负责人可以人工处理，或创建并登记 Workflow，再通过新的 Map 候选修改 executor_refs。
```

仅在 Registry 登记 Agent 不足以恢复自动执行。负责人还必须通过候选流程修改正式 Map 的 `executor_refs`，并完成正式发布。

## PendingHandoff 的状态边界

`PendingHandoff` 表示领域交接等待事实，不是 `TaskNode`、`DependencyEdge` 或 `ExecutionRecord`，也不属于 Redpanda 的 offset 状态。

它至少需要表达：

```text
pending_handoff_id
source_node_version_ref
dependency_edge_version_ref（如果已有正式边）
target_task_node_logical_id
target_node_version_ref（正式化后才有）
source_formal_revision_id
target_formal_revision_id（正式化后才有）
waiting_reason
status
created_at
resolved_at
resolved_event_id
```

典型 `waiting_reason`：

```text
target_not_formal
blocking_dependency_missing
activation_condition_unknown
executor_not_registered
human_action_required
```

队列不负责阻塞等待。处理原则是：

```text
Redpanda 消息被交接协调服务正常消费并提交 offset
    → 交接协调服务保存 PendingHandoff
    → 目标正式化或依赖条件变化时重新计算
    → 满足条件后生成新的 task_handoff_ready
```

`PendingHandoff` 是交接协调领域的等待事实，不是 Redpanda offset，也不是 Task Agent 的 `ExecutionRecord`。它不得成为 Task Agent 的本地隐式状态；具体权威存储和服务部署形态由交接协调服务决策票确定。

这样可以避免一个未满足条件的消息阻塞整个分区，也不会把领域等待状态伪装成队列消费状态。

## 依赖类型与通知行为

```text
information
    通知下游；是否触发执行由任务定义决定

blocking
    保存通知事实；blocks_until 满足后才可执行

conditional
    通知下游；激活条件成立后才可执行

alternative
    记录候选路径；不能让 Agent 自行猜测选择哪条路线
```

所有有效下游关系都可以产生通知事实，但只有以下条件同时满足时才生成 `task_handoff_ready`：

```text
目标 TaskNode 属于当前正式 MappingRevision
依赖边属于当前正式 MappingRevision
source/target 版本引用精确匹配
required_outputs 已满足
activation_condition 已满足或明确为无条件
executor_refs 指向已登记的 Workflow Agent
```

## 任务执行完成后的后续流程

Task Agent 完成一轮执行后，不直接向下游发布任务消息：

```text
Task Agent Worker
    → 写入草稿箱
    → 产生 draft_id
    → TaskNode Owner 审阅并提交候选
    → Centre Agent 预审
    → Project Owner 正式发布
    → 正式版本发布事件
    → 沿正式 DependencyEdge 生成新的下游通知
```

这避免 Agent 自己宣布正式交接，绕过候选、审核和正式版本治理。

如果当前正式 Map 没有下游 TaskNode，交接协调服务先记录待推进检测；确认当前确实没有任何后继时，发布：

```text
task_terminal_summary
```

邮件服务据此通知 Project Owner 或指定负责人。PO 不直接操作队列；如果 PO 决定继续路线，通过最高权限领域 MCP 创建新的 TaskNode/DependencyEdge 候选。新后继正式化后，交接协调服务自动重新计算并生成 `task_handoff_ready`。邮件发送成功只表示通知投递成功，不表示任务已完成或路线已正式推进。

## 与队列消费的边界

消息队列负责：

- 传递领域事件和任务交接事件；
- 按消息主题、分区和消费者组排队；
- 保存并提交 consumer offset；
- 支持至少一次投递和重放。

消息队列不负责：

- 判断候选是否可以正式化；
- 保存 TaskNode 或 DependencyEdge 正文；
- 根据 Registry 登记自动授予任务权限；
- 等待下游正式化；
- 代替领域服务判断激活条件；
- 将邮件发送成功解释为任务完成。

消息队列消费失败和任务业务失败也要分开：

```text
基础设施暂时不可用
    → 不提交 offset，等待重试

消息格式非法或无法配置
    → 记录错误或死信，避免无限重试

Worker 已明确失败
    → ExecutionRecord = failed，提交 offset

Worker waiting / completed / cancelled
    → 本轮处理完成，提交 offset
```

## 总体流程

```text
上游正式版本发布
    ↓
交接协调服务消费 downstream_dependency_notice
    ↓
查询当前正式 DependencyEdge
    ↓
为有效下游创建或更新 PendingHandoff
    ↓
目标未正式化？
    ├── 是：保存等待配置事实，通知负责人，不触发执行
    └── 否：检查输出和激活条件
              ↓
          条件未满足？
              ├── 是：保存 PendingHandoff，等待后续正式事件
              └── 否：检查 executor_refs
                        ↓
                    已登记 Workflow Agent？
                        ├── 是：交接协调服务发布 task_handoff_ready，Agent 执行
                        └── 否：交接协调服务生成 human_notification_intent，邮件通知负责人
```

核心原则是：**队列传递事件，正式 Map 决定路线，Registry 只提供身份事实，PendingHandoff 保存领域等待，`task_handoff_ready` 才触发 Agent。**
