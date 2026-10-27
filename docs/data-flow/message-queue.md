# 消息队列：正式版本到下游执行

本文描述 Research Mapping 正式版本发布后，如何通过消息队列通知下游、等待下游配置、选择 Workflow Agent 并触发一次执行。它只描述消息协作边界，不实现 Redpanda 客户端、邮件服务或领域管理 MCP。

消息语义的权威定义在[消息队列协作模型分支](../../.tickets/ai4-te1v.md)；交接协调服务的职责与部署形态在[交接协调服务的职责、存储边界与 centre-control 部署形态](../../.tickets/ai4-p5f3.md)。本文与两份票据冲突时以票据为准。

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

## 交接协调服务的边界

交接协调服务是一个位于中央服务侧的独立角色：仓库现有的 `centre-agents` 是执行候选预审的 Centre Agent，`research-map` 是 Research Mapping 领域服务，二者都不承担通用交接协调职责。它的源码位置与部署形态见 `sci-weave/centre-control/coordinator/`。

该角色的职责是：

- 消费 `sciweave.governance-events`，路由 `formal_revision_published` 与 `task_completed`；
- 查询当前正式 Mapping，而不是复制 TaskNode/DependencyEdge 正文；
- 判断正式节点、正式边、版本引用、所需输出和激活条件；
- 创建或更新 `PendingHandoff`；
- 条件满足时发布 `task_handoff_ready`；
- 没有可用自动执行主体时，通过 email-service MCP 发送 `human_notification_intent`。

它不负责修改正式 Mapping、授予执行权限、启动 Worker、执行 Centre Agent 预审或把邮件发送成功解释成任务完成。`PendingHandoff` 与 `HandoffDispatch` 归它自己的持久化边界，Task Agent、Centre Agent 与 email-service 只保存各自的执行或投递事实。

## 物理 topic 与逻辑频道

消息交接按接收目标和处理语义分成三个固定物理 topic：

```text
sciweave.dependency-notice
    → 保留 topic，目前没有任何生产者或消费者（未实现）

sciweave.task-handoff.<agent_id>
    → task_handoff_ready
    → task-workflow 的 Task Agent subscriber

sciweave.governance-events
    → candidate_created、candidate_head_updated、formal_revision_published、task_completed
    → 交接协调服务（formal_revision_published、task_completed）与 centre-workflow 的可扩展订阅者
```

首版没有 `sciweave.notification-intent`。`human_notification_intent` 与 `task_terminal_summary` 不经 Redpanda，由交接协调服务通过 email-service 的受鉴权 MCP `send_notification` 投递。

业务上每个目标 TaskNode 仍拥有独立逻辑频道；物理 topic 不按 TaskNode 或每个 Workflow 动态创建。任务交接消息以 `routing.partition_key = task_node_id` 作为分区键（同一节点的多个版本落在同一分区，才能保证版本间的先后顺序）。Centre Workflow 通过独立订阅声明和消费者组扩展；email-service 不消费任何 Redpanda topic。topic 订阅不构成授权来源，正式 `executor_refs` 仍是 TaskNode 执行关系权威。

三处目标中前两类是 Redpanda 消费者，email-service 不是。它们可以共享统一消息信封，但不得把三者都伪装成 `task_handoff_ready`：`task-workflow` 才能创建 Task Agent 的 `ExecutionRecord`；`centre-workflow` 订阅治理事件触发预审或其他中央 Workflow；email-service 只接受 MCP 调用投递人工通知。

### 消息信封

> **⚠️ 本节描述的是目标格式，尚未落地（2026-10-27）。**
>
> 线上三个生产者（交接协调服务、research-map、research-wiki）发的都是各自手写的扁平 dict，`shared/message-envelope/` 这个包**零调用方**。字段名、`schema_version` 的类型与有无、引用数组的形状，五份字段表（本节、信封包、协调器、research-map、research-wiki）目前互不一致；细节与迁移顺序见 [信封格式三分叉](../../.tickets/ai4-derq.md)。在迁移完成前，**不要按本节写新的消费者**——请按本节下方「兼容策略采用容忍式读取」那一段读真实消息。

所有 Redpanda 业务消息使用统一信封，业务字段放在 `payload`：

```json
{
  "message_id": "...",
  "message_type": "task_handoff_ready",
  "schema_version": 1,
  "dedupe_key": "...",
  "occurred_at": "...",
  "published_at": "...",
  "producer": {
    "service": "handoff-coordinator",
    "instance_id": "..."
  },
  "routing": {
    "partition_key": "task:data-analysis",
    "target_agent_id": "agent:data-analysis-workflow"
  },
  "payload": {}
}
```

消息体使用 JSON（UTF-8），不引入 Avro 或 Protobuf，也不使用 Redpanda 自带的 Schema Registry。

`schema_version` 是整数精确匹配，首版为 `1`，不存在次版本号。`dedupe_key` 是业务幂等键，重试发布时保持不变。消费方遇到未知 `message_type`、`schema_version` 不等、错误目标 Agent 或正式版本校验失败时，必须写入可观察的错误状态，不得静默丢弃。

兼容策略采用容忍式读取：`schema_version` 相等的消息一律可消费，消费方必须忽略 payload 中的未知字段；新增字段必须是可选的并带文档化默认值；已有字段名不得改变用途；只有删除字段、改变字段语义或改变必填性才升版本。升至 `2` 是破坏性迁移，需要新旧并存窗口或同步升级。

信封的 schema、序列化、校验与构造逻辑落在中央多项目共用的纯协议包 `sci-weave/centre-control/shared/message-envelope/`，不携带 Kafka 客户端。该包由 [实现消息信封纯协议包](../../.tickets/ai4-3zxu.md) 承接。

详细的目标类型、可扩展订阅和启动恢复流程见 [`message-delivery-recovery.md`](message-delivery-recovery.md)。

## 两层消息语义

上游正式版本发布后，消息系统区分“通知下游”和“允许执行”两层语义。

### 下游依赖通知

`sciweave.governance-events` 上的 `formal_revision_published` 表示：

> 上游已经产生新的正式事实，相关下游需要知道这次变化。

它不会启动 Worker。它可以用于：

- 通知下游负责人；
- 记录等待中的交接；
- 等待目标 TaskNode 正式化；
- 等待其他前置节点完成；
- 等待激活条件变为可判断或满足；
- 等待负责人创建并登记 Workflow Agent。

同一 topic 上的 `task_completed` 表示某个 Task Agent 已完成一轮执行并写出草稿，用于解除下游的完成条件。

### 可执行交接

`task_handoff_ready` 表示：

> 目标 TaskNode 和依赖边都属于正式 Map，所需输出和激活条件已经满足，且存在正式配置的执行主体，可以开始一轮执行。

只有 `task_handoff_ready` 才能进入 Task Agent 的消费者组并创建 ExecutionRecord。

```text
formal_revision_published / task_completed
    → sciweave.governance-events
    → 交接协调服务
    → 检查正式目标、依赖输出和激活条件
    → task_handoff_ready
    → sciweave.task-handoff.<agent_id>
    → 目标 Task Agent subscriber
    → ExecutionRecord
    → Worker
```

`sciweave.governance-events` 有两个消费者，各自使用独立消费者组：交接协调服务订阅并路由 `formal_revision_published` 与 `task_completed`，Centre Agent 订阅 `candidate_created`、`candidate_head_updated` 与 `formal_revision_published` 观察治理事件，但不负责全局依赖重算。`sciweave.dependency-notice` 是保留 topic，目前没有生产者也没有消费者；email-service 不消费任何 Redpanda topic。

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
  "message_id": "msg:...",
  "message_type": "task_handoff_ready",
  "schema_version": 1,
  "dedupe_key": "handoff:edge-version-2:formal-revision-12",
  "occurred_at": "...",
  "published_at": "...",
  "producer": {
    "service": "handoff-coordinator"
  },
  "routing": {
    "partition_key": "task:data-analysis",
    "target_agent_id": "agent:data-analysis-workflow"
  },
  "payload": {
    "mapping_domain_id": "mapping:project-1",
    "target_agent_id": "agent:data-analysis-workflow",
    "task_node_id": "task:data-analysis",
    "target_node_version_ref": "task-version:2",
    "trigger_revision_id": "formal-revision:12",
    "pending_handoff_id": "pending:handoff-2",
    "dependency_edge_version_refs": [
      {
        "logical_id": "edge:literature-to-analysis",
        "version_id": "edge-version:2"
      }
    ],
    "upstream_source_refs": [
      {
        "logical_id": "task:literature-review",
        "version_id": "task-version:1"
      }
    ],
    "executor_ref_snapshot": ["agent:data-analysis-workflow"]
  }
}
```

`dependency_edge_version_refs` 是该节点在当前正式快照中的全部入边版本引用，只有一条时仍用数组形式。`executor_ref_snapshot` 只用于审计，subscriber 仍须按当前正式 Map 校验执行关系。

`executor_ref_snapshot` 记录完整的 `executor_refs`，`payload.target_agent_id` 记录**实际被选中**的那一个：按声明顺序取第一个可用的 Agent，全部不可用则不发本条消息，转人工通知。

随后：

```text
sciweave.task-handoff.<agent_id>
    → target agent_id 的 topic
    → gateway/subscriber
    → queued ExecutionRecord
    → Worker Lease
    → Worker 执行一轮 Workflow
```

首版不为每个 TaskNode 动态创建物理 Redpanda topic。任务交接使用按 `agent_id` 隔离的 topic 模板 `sciweave.task-handoff.<agent_id>`；一个 Agent 可负责多个 TaskNode，同一 Agent 的多个实例共享对应消费者组并竞争消费。业务上每个目标 TaskNode 仍拥有独立逻辑频道，消息以 `routing.partition_key = task_node_id` 作为分区键。

## 没有可用 Workflow Agent

如果目标 TaskNode 已正式化、依赖也满足，但：

- `executor_refs` 为空；
- 只配置了人工处理；
- `executor_refs` 指向未登记的 `agent_id`；或
- 目标 Agent 已注销或没有可用运行实例；

则不发布 `task_handoff_ready`。交接协调服务通过 email-service 的受鉴权 MCP `send_notification` 提交一条 `human_notification_intent`，不经 Redpanda。

上述原因不共用一个 `notification_kind`，因为它们要求的动作不同：

```text
executor_refs 为空                     → workflow_binding_required
executor_refs 指向未登记的 agent_id    → workflow_load_failed
已注销 / 无可用实例 / 只配置人工处理    → agent_unavailable
入边带激活条件、协调无法自动判定       → dependency_condition_hold
```

`dependency_condition_hold` 的触发点不在本节「没有可用 Workflow Agent」的判断里：入边带 `activation_condition` 且协调服务无法自动判定时不得猜条件，只能挂起并通知该节点的 `task_owner_id`。第四种 kind 与通知去重键的粒度见 [消息队列协作模型分支](../../.tickets/ai4-te1v.md) 的「2026-10-27 修订」。

收件人一律是该节点的 TaskNode Owner，取自 `TaskNode.task_owner_id`；email-service 按这个 `principal_id` 经 Registry 解析邮箱并发送邮件。邮件说明：

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
resolved_message_id
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

`PendingHandoff` 是交接协调领域的等待事实，不是 Redpanda offset，也不是 Task Agent 的 `ExecutionRecord`。它不得成为 Task Agent 的本地隐式状态；它归交接协调服务自己的持久化边界。

这样可以避免一个未满足条件的消息阻塞整个分区，也不会把领域等待状态伪装成队列消费状态。

## 依赖类型与通知行为

```text
information
    通知下游，产生通知事实与 PendingHandoff；是否触发执行由任务定义决定

blocking
    保存通知事实；blocks_until 满足后才可执行

conditional
    激活条件能自动判定时按判定结果处理；不能判定时不得自动放行
    进入 PendingHandoff(status=waiting, waiting_reason=activation_condition_unknown)
    并生成 human_notification_intent，由人工判断或补充信息

alternative
    按 alternative_group_id 归组记录候选路径；不能让 Agent 自行猜测选择哪条路线
    同组内没有可判定的激活条件时，走与 conditional 相同的人工等待路径
```

不允许把任何 `dependency_kind` 一律当作「全部上游完成即放行」。

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

如果当前正式 Map 没有下游 TaskNode，交接协调服务先记录待推进检测；确认当前确实没有任何后继时，通过 email-service 的受鉴权 MCP 提交一条 `task_terminal_summary` 通知，不经 Redpanda。

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
    → 写入可观察 Inbox 错误状态，不静默丢弃

Worker 已明确失败
    → ExecutionRecord = failed，提交 offset

Worker waiting / completed / cancelled
    → 本轮处理完成，提交 offset
```

交接协调服务自己的派发失败不走队列重试，而是记在 `HandoffDispatch` 上：

```text
max_attempts       = 5
backoff_initial    = 1s
backoff_max        = 60s
backoff_strategy   = 指数退避（1s, 2s, 4s, 8s, 16s，封顶 60s）
```

参数由环境变量配置，默认值如上。`attempt_count` 达到上限仍未确认发布成功的 dispatch 转入 `dead`，只保留可观察记录，不自动重放，由人工经运维查询处理。`result_unknown` 表示可能已发出，`failed` 表示确定未发出，二者不可合并。

## 总体流程

```text
上游正式版本发布
    ↓
交接协调服务消费 sciweave.governance-events
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
                        ├── 是：发布 task_handoff_ready 到 sciweave.task-handoff.<agent_id>，Agent 执行
                        └── 否：经 email-service MCP 提交 human_notification_intent，邮件通知负责人
```

核心原则是：**队列传递事件，正式 Map 决定路线，Registry 只提供身份事实，PendingHandoff 保存领域等待，`task_handoff_ready` 才触发 Agent。**
