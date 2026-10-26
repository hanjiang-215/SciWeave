# 消息交接恢复与多目标订阅

本文记录消息交接在三类接收目标之间的边界，以及交接协调服务启动后的恢复流程。它补充 [`message-queue.md`](message-queue.md) 的事件流，不实现 Redpanda 客户端、邮件服务或具体 Workflow。

交接协调服务通过 Research Mapping 的只读领域接口读取正式快照；具体采用 MCP Streamable HTTP、内部 HTTP 或其他稳定传输方式，由[Research Mapping 正式快照查询接口与交接协调服务访问边界](../../.tickets/ai4-2982.md)裁决（该票已关闭，结论为经 research-map 管理 MCP 的 `get_formal_mapping_at_revision` 读取）。交接协调服务不得直连 Research Mapping SQLite 或 TerminusDB。

研究员端新建 `task-workflow` 后的订阅发现、消费者组和历史消息恢复，由[研究员 Task Agent 动态订阅 task-workflow 交接消息](../../.tickets/ai4-nfty.md)收敛（该票已关闭）；本文件只要求交接事件携带稳定的目标 Agent 和目标节点版本引用。

消息信封字段、消息类型与消费者组的权威定义在[消息队列协作模型分支](../../.tickets/ai4-te1v.md)。

## 目标类型不是同一种交接语义

交接协调服务可以根据同一份正式 Mapping 判断多个下游目标，但不把三类目标压成同一种 `task_handoff_ready`：

```text
sciweave.governance-events
    → 交接协调服务统一重算正式依赖（formal_revision_published、task_completed）
        ├── task-workflow    → sciweave.task-handoff.<agent_id> → task_handoff_ready
        ├── centre-workflow  → 订阅同一 topic 的治理事件
        └── email-service    → 受鉴权 MCP send_notification → human_notification_intent
```

前两类是 Redpanda 消费者，第三类不是。email-service 不订阅任何 topic，只接受 MCP 调用；而 `centre-workflow` 订阅的治理事件由领域管理流程生产，不由交接协调服务生产。

### task-workflow

`task-workflow` 表示目标 TaskNode 的科研执行 Workflow。只有正式节点、正式边、版本引用、所需输出、激活条件和 `executor_refs` 均满足时，才发布 `task_handoff_ready`。

消息至少携带：

```text
message_id
message_type = task_handoff_ready
schema_version
dedupe_key
routing.target_agent_id
routing.partition_key = target_node_id
payload.target_node_id
payload.target_node_version_ref
payload.mapping_domain_id
payload.pending_handoff_id
payload.trigger_revision_id
payload.upstream_source_refs
payload.executor_ref_snapshot
```

消息由目标 TaskNode 对应的 Task Agent subscriber 消费，创建 `queued ExecutionRecord`、获取 Worker Lease 并启动 Worker。

### centre-workflow

`centre-workflow` 表示中央服务器上的治理 Workflow。当前只提供候选预审 Workflow，后续可以增加其他中央 Workflow，因此订阅必须是可扩展的。

Centre Agent 当前订阅：

```text
candidate_created
candidate_head_updated
formal_revision_published
```

它们发布到：

```text
sciweave.governance-events
```

Centre Agent 收到事件后，通过两套独立领域管理 MCP 拉取当前候选快照，执行预审并写入预审报告。它不消费 `task_handoff_ready`，也不负责判断“下一步该谁动”。

后续新增 Centre Workflow 时，使用独立的订阅声明和消费者组，例如：

```text
workflow_id
workflow_kind
subscribed_event_types
mapping_domain_scope
consumer_group
```

新增 Workflow 只增加订阅者，不改变事件生产者，也不改变 Task Agent 的执行语义。每个 Centre Workflow 使用独立消费者组，避免一个 Workflow 消费后让另一个 Workflow 丢失事件。

### email-service

`email-service` 不是 Workflow Agent，而是人工通知投递服务。它**不消费任何 Redpanda topic**，只以受鉴权 MCP `send_notification` 接受调用。调用方是交接协调服务（以及需要通知研究员的端侧 Work Agent）。

业务对象仍是 `human_notification_intent`，至少携带：

```text
notification_id
notification_kind
recipient_principal_id
pending_handoff_id
source_formal_revision_id
target_task_node_logical_id
reason
dedupe_key
schema_version
```

`recipient_principal_id` 只有一个，是**需要动手的那个人**，不是抄送名单。角色由 `notification_kind` 决定，调用方不得自行挑选收件人：

| `notification_kind` | 触发条件 | 收件人角色 | 收件人来源 |
| --- | --- | --- | --- |
| `workflow_binding_required` | 目标节点 `executor_refs` 为空 | 该节点的 TaskNode Owner | `TaskNode.task_owner_id` |
| `workflow_load_failed` | `executor_refs` 指向未登记的 `agent_id` | 该节点的 TaskNode Owner | `TaskNode.task_owner_id` |
| `agent_unavailable` | 执行者已注销、无可用实例，或该节点只配置人工处理 | 该节点的 TaskNode Owner | `TaskNode.task_owner_id` |
| `dependency_condition_hold` | 入边带 `activation_condition`，协调服务无法自动判定 | 该节点的 TaskNode Owner | `TaskNode.task_owner_id` |
| `task_terminal_summary` | 派发成功的节点无后继 | 项目负责人 | `formal_mapping_revision.published_by`（见 [ADR-0004](../adr/0004-po-recipient-from-latest-approver.md)） |

前三种指向「把这个任务跑起来」，要建 Workflow、修 `agent_id` 或接管执行；`dependency_condition_hold` 指向「条件待判定」，要人判断或补充信息；最后一种指向「这条路线到头了，接下来做什么」，是项目负责人的决策。因此不存在把它们合并成一个 `notification_kind` 的做法。`dependency_condition_hold` 的来源见 [消息队列协作模型分支](../../.tickets/ai4-te1v.md) 的「2026-10-27 修订」。

`task_owner_id` 是 TaskNode 文档的必填字段，缺失表示数据损坏而非正常分支。此时不猜测收件人、不生成通知，保留 `PendingHandoff(status=waiting)` 并记录 `recipient_unresolved:task_owner_id_missing`，由人工修数据。

首版没有 `sciweave.notification-intent` topic。`task_terminal_summary` 同样走 MCP，不进队列。

email-service 记录发送成功、失败和重试状态。邮件投递成功不代表依赖满足、任务完成、PendingHandoff 解决或正式路线推进。

## 消息信封

三类消息共享同一信封，但物理 topic 和消费组按处理语义隔离：

```json
{
  "message_id": "msg:...",
  "message_type": "...",
  "schema_version": 1,
  "dedupe_key": "...",
  "occurred_at": "...",
  "published_at": "...",
  "producer": {
    "service": "...",
    "instance_id": "..."
  },
  "routing": {
    "partition_key": "...",
    "target_agent_id": "..."
  },
  "payload": {}
}
```

`routing.target_agent_id` 表达目标 Agent，但不作为权限来源。正式 `executor_refs` 决定 TaskNode 执行关系；Centre Workflow 的订阅配置决定它订阅哪些治理事件；Registry 只提供身份和实例登记事实。

信封的 schema、序列化、校验与构造逻辑落在 `sci-weave/centre-control/shared/message-envelope/`，是纯协议包，不携带 Kafka 客户端。消息体为 JSON（UTF-8），`schema_version` 整数精确匹配，兼容策略见 [`message-queue.md`](message-queue.md)「统一消息信封」。

Inbox 中未找到 Workflow 卡片、版本不兼容、加载失败或进程启动失败时，消息保持在 Inbox，不启动下一轮 Worker，不修改正式 Map；记录配置错误并通过 email-service MCP 提交 `human_notification_intent`，待 binding 或卡片修复后重新扫描。


服务启动时不能只扫描 Redpanda，也不能把每条历史消息全部重放。恢复分为三层：

### 第一层：未提交 offset

消费者使用原来的 consumer group 连接 Redpanda：

```text
进程崩溃
    → 当前消息处理未提交 offset
    → 服务重启
    → 同一 consumer group 重新收到该消息
```

不更换 consumer group，不把恢复逻辑建立在 `latest` 上。业务处理完成后才提交 offset，并通过 `message_id` 或 `dedupe_key` 幂等。

### 第二层：未完成的 PendingHandoff 和 HandoffDispatch

交接协调服务启动后扫描自己的持久化状态：

```text
PendingHandoff.status ∈ {waiting, ready, dispatched_unknown}
HandoffDispatch.status ∈ {result_unknown, failed}
```

`done`、`superseded`、`published` 与 `dead` 不参与启动扫描：它们要么已终结，要么只保留记录等待人工处理。

恢复流程为：

```text
初始化本地存储
    → 扫描 PendingHandoff
    → 扫描 HandoffDispatch
    → 按稳定顺序重新计算或重发
    → 启动正常消息消费
```

`HandoffDispatch` 用来覆盖“消息已发出但服务在记录发送结果前崩溃”的窗口：

```text
dispatch_id
pending_handoff_id
output_message_id
dedupe_key
message_type
target_agent_id
status
attempt_count
last_error
created_at
completed_at
```

重试参数默认值：

```text
max_attempts       = 5
backoff_initial    = 1s
backoff_max        = 60s
backoff_strategy   = 指数退避（1s, 2s, 4s, 8s, 16s，封顶 60s）
```

由环境变量配置。`attempt_count` 达到 `max_attempts` 仍未确认发布成功的 dispatch 转入 `dead`，保留记录但不自动重放。

重复发布由 `dedupe_key` 和下游消费者幂等共同保护，不追求跨数据库与消息队列的精确一次事务。

### 第三层：消息过期后的补偿扫描

Redpanda 保留期之外的消息不能作为永久事实来源。服务应依据正式 Mapping 做补偿重算：

```text
当前正式 Mapping
    + 未完成 PendingHandoff
    + 未完成 HandoffDispatch
    → 稳定业务键幂等重算
```

补偿扫描不是每次启动都从历史 topic 开始读取，也不修改正式 Mapping。它只重新生成当前条件下仍然有效的通知、执行交接或人工通知意图。

## 失败边界

```text
Redpanda 暂时不可用
    → 不提交 offset，等待消费者重连

消息格式非法且无法重试
    → 写入可观察的 Inbox 错误状态并提交 offset，不阻塞分区
    → 不新建独立死信 topic

正式 Mapping 条件不满足
    → 保存 PendingHandoff，提交 governance-events offset

交接事件发送结果未知
    → 保存 HandoffDispatch(status=result_unknown)，启动时重试
    → 达到 max_attempts 转 dead，只留记录不自动重放

Task Agent 明确执行失败
    → Task Agent 写 ExecutionRecord=failed，按 Work Agent 规则提交 task-handoff offset

邮件发送失败
    → email-service 记录 retryable，不能回滚正式 Mapping 或阻塞 Task Agent
```

## PO 操作与根任务消息

PO 不直接操作 Redpanda。所有候选创建、混合候选、正式化、返修指派和根任务分派均通过最高权限领域 MCP 完成。

没有上游 DependencyEdge 的正式根 TaskNode，由 PO 调用幂等的 `dispatch_root_task` 发送第一条 `task_handoff_ready`。该工具验证正式 Mapping、`executor_refs` 和幂等键，然后由消息服务完成实际发布。

**无入边节点不自动派发。** 交接协调服务在任何正式版本发布时都不为无入边节点生成 `task_handoff_ready`；「无入边」在依赖重算里是不满足可自动派发条件，不是条件平凡满足。

候选裁决不支持 `defer`：PO 必须选择 `formalize`、`request_revision` 或 `reject`。返修必须指定唯一 `repair_owner_id`，由负责人自己的 Task Agent 执行；Centre Workflow 不负责返修。

## 当前没有后继 TaskNode

正式版本发布后，交接协调服务检查当前正式 Mapping 的后继关系：

```text
存在正式后继且条件满足
    → task_handoff_ready

存在后继但尚未满足正式化/依赖/Agent 条件
    → 保存待推进交接事实
    → 后续正式事件触发重新计算

确认当前没有任何后继
    → 经 email-service MCP 提交 task_terminal_summary
    → Project Owner
```

“当前没有后继”不是错误，也不自动创建新任务。PO 如果决定继续路线，通过领域 MCP 创建新的 TaskNode/DependencyEdge 候选；新后继正式化后，交接协调服务自动重新计算并发送任务交接。

### Task Agent topic 生命周期

- Agent 注册完成且具备接收任务条件时创建 `sciweave.task-handoff.<agent_id>`；
- Agent 注销不删除 topic、不删除 Registry 记录，只标注注销或不可用；
- Agent 离线时保留 topic、consumer group 和未消费消息；
- topic 创建、订阅、加载或启动失败不修改正式 Map，必须形成可观察配置错误并支持人工处理；
- 不执行自动删除 topic 的原子操作。历史清理和保留期另按消息基础设施策略处理。

### Task Agent consumer group

同一 `mapping_domain_id` 与 `agent_id` 派生一个稳定消费者组：

```text
sciweave.task-workflow.<mapping_domain_id>.<agent_id>
```

同一 Agent 的多个 `agent_instance_id` 共享该消费者组并竞争消费；实例重新上线后继续消费未提交 offset。


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

首版没有 `sciweave.notification-intent`。人工通知由交接协调服务通过 email-service 的受鉴权 MCP `send_notification` 提交，不经 Redpanda。

这些是固定物理 topic，不按 TaskNode 或每个 Workflow 动态创建 topic。TaskNode 的逻辑频道通过消息中的目标节点引用和分区键表达；Centre Workflow 通过独立订阅声明和消费者组扩展。
