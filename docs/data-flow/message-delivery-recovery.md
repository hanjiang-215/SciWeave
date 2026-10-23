# 消息交接恢复与多目标订阅

本文记录消息交接在三类接收目标之间的边界，以及交接协调服务启动后的恢复流程。它补充 [`message-queue.md`](message-queue.md) 的事件流，不实现 Redpanda 客户端、邮件服务或具体 Workflow。

交接协调服务通过 Research Mapping 的只读领域接口读取正式快照；具体采用 MCP Streamable HTTP、内部 HTTP 或其他稳定传输方式，暂由[Research Mapping 正式快照查询接口与交接协调服务访问边界](../../.tickets/ai4-2982.md)裁决。交接协调服务不得直连 Research Mapping SQLite 或 TerminusDB。

研究员端新建 `task-workflow` 后的订阅发现、消费者组和历史消息恢复，由[研究员 Task Agent 动态订阅 task-workflow 交接消息](../../.tickets/ai4-nfty.md)收敛；本文件只要求交接事件携带稳定的目标 Agent 和目标节点版本引用。

## 目标类型不是同一种交接语义

交接协调服务可以根据同一份正式 Mapping 判断多个下游目标，但不把三类目标压成同一种 `task_handoff_ready`：

```text
dependency-notice
    → 交接协调服务统一重算正式依赖
        ├── task-workflow    → task_handoff_ready
        ├── centre-workflow  → centre_review_trigger
        └── email-service    → human_notification_intent
```

### task-workflow

`task-workflow` 表示目标 TaskNode 的科研执行 Workflow。只有正式节点、正式边、版本引用、所需输出、激活条件和 `executor_refs` 均满足时，才发布 `task_handoff_ready`。

消息至少携带：

```text
target_kind = task-workflow
target_node_version_ref
target_agent_id
source_node_version_ref
dependency_edge_version_ref
formal_revision_id
required_outputs
business_key
event_id
schema_version
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

`email-service` 不是 Workflow Agent，而是人工通知投递服务。它消费：

```text
sciweave.notification-intent
```

消息类型为 `human_notification_intent`，至少携带：

```text
notification_id
notification_kind
recipient_principal_id
task_owner_id 或 project_owner_id
pending_handoff_id
source_formal_revision_id
target_task_node_logical_id
reason
dedupe_key
schema_version
```

邮件服务记录发送成功、失败和重试状态。邮件投递成功不代表依赖满足、任务完成、PendingHandoff 解决或正式路线推进。

## 消息封套

三类消息可以共享序列化封套，但物理 topic 和消费组按处理语义隔离：

```json
{
  "event_id": "event:...",
  "event_type": "...",
  "schema_version": 1,
  "mapping_domain_id": "mapping:...",
  "occurred_at": "...",
  "dedupe_key": "...",
  "target": {
    "kind": "task-workflow | centre-workflow | email-service",
    "id": "..."
  },
  "payload": {}
}
```

`target.kind` 表达目标类型，但不作为权限来源。正式 `executor_refs` 决定 TaskNode 执行关系；Centre Workflow 的订阅配置决定它订阅哪些治理事件；Registry 只提供身份和实例登记事实。

## 启动恢复的三层模型

服务启动时不能只扫描 Redpanda，也不能把每条历史消息全部重放。恢复分为三层：

### 第一层：未提交 offset

消费者使用原来的 consumer group 连接 Redpanda：

```text
进程崩溃
    → 当前消息处理未提交 offset
    → 服务重启
    → 同一 consumer group 重新收到该消息
```

不更换 consumer group，不把恢复逻辑建立在 `latest` 上。业务处理完成后才提交 offset，并通过 `event_id` 或业务键幂等。

### 第二层：未完成的 PendingHandoff 和 HandoffDispatch

交接协调服务启动后扫描自己的持久化状态：

```text
PendingHandoff.status ∈ {waiting, retryable, ready}
HandoffDispatch.status ∈ {pending, unknown, retryable}
```

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
output_event_id
dedupe_key
status
attempt_count
last_error
created_at
completed_at
```

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
    → 记录错误并进入死信，不无限阻塞分区

正式 Mapping 条件不满足
    → 保存 PendingHandoff，提交 dependency-notice offset

交接事件发送结果未知
    → 保存 HandoffDispatch(status=unknown)，启动时重试

Task Agent 明确执行失败
    → Task Agent 写 ExecutionRecord=failed，按 Work Agent 规则提交 task-handoff offset

邮件发送失败
    → notification intent 保持 retryable，不能回滚正式 Mapping 或阻塞 Task Agent
```

## PO 操作与根任务消息

PO 不直接操作 Redpanda。所有候选创建、混合候选、正式化、返修指派和根任务分派均通过最高权限领域 MCP 完成。

没有上游 DependencyEdge 的正式根 TaskNode，由 PO 调用幂等的 `dispatch_root_task` 发送第一条 `task_handoff_ready`。该工具验证正式 Mapping、`executor_refs` 和幂等键，然后由消息服务完成实际发布。

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
    → 发送 task_terminal_summary
    → notification-intent
    → Project Owner
```

“当前没有后继”不是错误，也不自动创建新任务。PO 如果决定继续路线，通过领域 MCP 创建新的 TaskNode/DependencyEdge 候选；新后继正式化后，交接协调服务自动重新计算并发送任务交接。

## 当前固定 topic

```text
sciweave.dependency-notice
    → 交接协调服务

sciweave.task-handoff.<agent_id>
    → task-workflow 的 Task Agent subscriber

sciweave.governance-events
    → centre-workflow 的可扩展订阅者

sciweave.notification-intent
    → email-service 或其他人工通知投递服务
```

这些是固定物理 topic，不按 TaskNode 或每个 Workflow 动态创建 topic。TaskNode 的逻辑频道通过消息中的目标节点引用和分区键表达；Centre Workflow 通过独立订阅声明和消费者组扩展。
