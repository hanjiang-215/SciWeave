---
id: ai4-te1v
status: closed
deps: []
links: []
created: 2026-10-18T15:18:52Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [wayfinder:grilling]
---
# 消息队列协作模型分支

为 SciWeave 多人、多 Agent 协作厘清消息模型与交接语义；已有 humans/dev/消息队列协作设计.md 作为讨论起点。产品已选定 Redpanda，本票只定义主题、分区、消费者组、载荷与投递语义，不做产品选型。

> 修订（2026-10-21）：原文为「当前只开工单，不选消息队列产品或协议，也不进入实现」。Redpanda 已选定并记入 `docs/TECH_STACK.md`，本票不再负责选型。

## Acceptance Criteria

- [x] 明确逻辑 topic 家族与物理 topic 的关系，不按 TaskNode 或 Workflow 实例动态创建 topic。
- [x] 明确 `dependency-notice`、`task-handoff`、`governance-events` 的物理 topic、消息类型和消费者关系。
- [x] 明确首版不消费 Redpanda `notification-intent`，通知通过 email-service MCP 传递。
- [x] 明确 `task_handoff_ready` 的 Agent 路由、`target_node_id` 分区键和消费者组命名。
- [x] 明确统一消息信封、schema 版本、幂等键和核心业务载荷。
- [x] 明确至少一次投递、业务完成后提交 offset、重复投递幂等和失败处置。
- [x] 明确队列短期恢复、端侧 Inbox、协调记录和消息过期补偿的三层恢复边界。
- [x] 明确消息信封的归属：中央多项目共用的纯协议包 `sci-weave/centre-control/shared/message-envelope/`，不含任何 Kafka 客户端。
- [x] 明确 Python 客户端选型为 `confluent-kafka`，版本约束与锁文件要求见下文「依赖边界」。
- [x] 明确 `dependency_kind` 四种取值在首版的处理口径。
- [x] 明确根任务只由 PO 的 `dispatch_root_task` 触发，无入边节点不自动派发。
- [x] 明确 `HandoffDispatch` 幂等键不含触发 revision，同一节点版本同一消息类型只派发一次。
- [x] 明确 `executor_refs` 多值时按声明顺序选第一个可用的 Agent，全部不可用转人工。
- [x] 明确 `PendingHandoff` 与 `HandoffDispatch` 的状态词表以现有实现为准，并固定 `max_attempts` 默认值。
- [x] 明确 `HandoffDispatch` 的重试上限与退避参数。
- [x] 明确 `task_completed` 的发布时点与返修后是否重发的规则。
- [x] 明确人工通知的收件人角色由 `notification_kind` 决定，且每条通知只有一个收件人。
- [x] 明确消息序列化为 JSON（UTF-8），不使用 Avro、Protobuf 或 Schema Registry。
- [x] 明确 `schema_version` 为整数精确匹配，采用容忍式读取并禁止改动已有字段语义。

- [x] 主题划分与订阅关系：四个固定物理 topic 及 task-handoff 模板
- [x] 分区与分区键：目标节点逻辑 ID 作分区键，同节点有序、跨节点可并发
- [x] 消费者组命名与隔离：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`，多实例竞争消费
- [x] offset 提交时机：业务完结后提交，至少一次投递＋业务键去重，不追求精确一次
- [x] auto.offset.reset：首次启动/新组用 `earliest` 才能读到注册前的历史消息
- [x] 保留期与过期恢复：默认保留期内消费持久化，过期后由正式 Mapping 补偿重算兜底
- [x] 载荷与封套：统一信封 + 精确版本引用 + target_agent_id，topic 隔离不替代 `executor_refs` 鉴权
- [x] 失败边界：基础设施临时不可用不提交 offset；格式非法入死信；Worker 明确失败提交 offset

## Current design boundary

本票现在承载 Redpanda 已选定基础设施之上的消息语义，不承载具体客户端实现。逻辑 topic 家族与物理 topic 分开定义：

- `dependency-notice` 家族使用物理 topic `sciweave.dependency-notice`。
- `task-handoff` 家族使用 `sciweave.task-handoff.<agent_id>`；不按 TaskNode、Workflow 实例或 ExecutionRecord 动态创建 topic。
- `governance-events` 家族使用物理 topic `sciweave.governance-events`；不同中央 Workflow 使用不同 consumer group 隔离消费。
- 首版不使用 `sciweave.notification-intent`。`human_notification_intent` 通过 email-service 的受鉴权 MCP 传递，email-service 不消费 Redpanda 通知 topic。
- `dependency-notice` 的主消费者是 handoff coordinator，负责读取正式 Mapping、重算依赖、维护 `PendingHandoff` 和 `HandoffDispatch`，不能直接创建 Task Agent 的 `ExecutionRecord`。
- `task-workflow` 接收 `task_handoff_ready` 并创建 Task Agent 执行；`centre-workflow` 及后续中央 Workflow 订阅治理事件。
- `TaskNode.executor_refs` 决定 Task Agent 执行资格；Registry 只提供身份和实例登记事实，不授予权限。
- `task_handoff_ready` 使用 `target_node_id` 作为分区键；消息载荷仍精确引用源节点版本、目标节点版本、DependencyEdge 版本和正式 Mapping 版本。
- 消息采用至少一次投递；同一目标按顺序处理；消费者完成业务处理后提交 offset；重复投递使用 `dedupe_key` 和本地唯一约束幂等处理。
- 服务启动恢复采用三层模型：同一消费者组继续消费未提交 offset；扫描未完成的 `PendingHandoff`、`HandoffDispatch` 和端侧 Inbox；消息过期后依据正式 Mapping 与未完成本地事实补偿重算。
- 队列保留期只是短期离线恢复窗口，不是业务事实保存期限。消息过期后由协调事实和正式 Mapping 补偿，不新增独立死信 topic。
- `centre-agents` 是 Centre Workflow 的预审实现，不承担全局依赖重算；PO 的候选裁决和根任务分派通过最高权限领域 MCP 完成，根任务使用幂等 `dispatch_root_task`，无入边节点不自动派发。

### 首版消息类型

- `sciweave.dependency-notice`：`formal_revision_published`、`task_completed`。
- `sciweave.task-handoff.<agent_id>`：`task_handoff_ready`。
- `sciweave.governance-events`：`candidate_created`、`candidate_head_updated`、`formal_revision_published`。
- `human_notification_intent`、`task_terminal_summary` 不进入首版 Redpanda；`task_failed` 不触发下游完成，保存在 Task Agent 执行事实中；`root_task_dispatched` 不作为额外事件，根任务直接产生 `task_handoff_ready`。

### 统一消息信封

所有 Redpanda 业务消息使用统一信封，业务字段放在 `payload`：

- `message_id`：一次发布消息的唯一标识。
- `message_type`：消息类型。
- `schema_version`：消息 schema 版本，首版为整数 `1`；按「序列化与 schema 版本兼容」一节判定，不做次版本号。
- `dedupe_key`：业务幂等键，重试发布时保持不变。
- `occurred_at`、`published_at`：事件发生和发布的时间。
- `producer`：生产服务及可选实例标识。
- `routing`：分区键及任务交接时的 `target_agent_id`。
- `payload`：业务载荷。

`task_handoff_ready` 的载荷至少包含 `target_agent_id`、`target_node_id`、`target_node_version_ref`、`mapping_domain_id`、`pending_handoff_id`、`trigger_revision_id`、`dependency_edge_version_refs`、`upstream_source_refs` 和 `executor_ref_snapshot`。`executor_ref_snapshot` 仅用于审计，不能替代当前正式 Map 校验。

`dependency_edge_version_refs` 是该目标节点在当前正式快照中的所有入边版本引用。它与 `upstream_source_refs` 一起构成「这条交接依据的是哪几个正式版本」的完整答案；只有一个时会退化为单元素数组，仍使用数组形式。

`task_completed` 的载荷至少包含 `mapping_domain_id`、`task_node_id`、`completed_version_ref`、`execution_id`、`draft_id`、`completed_at` 和 `result_ref`；只有草稿箱写入成功且 ExecutionRecord 保存 `completed` 与 `draft_id` 后才发布。

### 消息生产者与消费者

- `formal_revision_published` 由领域正式化流程生产；handoff coordinator 与 Centre Workflow 按各自 consumer group 消费，不由 PO、Task Agent 或 coordinator 伪造。
- `task_completed` 由 Task Agent Worker 在 ExecutionRecord 保存 `completed` 且草稿箱写入成功后生产；handoff coordinator 消费。邮件发送成功、Worker 进入 `waiting`、失败或取消均不产生该事件。
- `task_handoff_ready` 由 handoff coordinator 唯一生产；根任务 `dispatch_root_task` 复用同一发布端口，且无入边节点不自动派发。Task Agent 和 Centre Agent 不得直接发布。
- `candidate_created`、`candidate_head_updated` 由候选领域管理流程生产，由 Centre Workflow 消费；Centre Agent 不生产治理事件。
- 首版治理事件的具体生产调用点必须由领域管理实现票保证与相应领域事实写入一致；本票不规定跨服务原子事务实现。

### 消费者组

- handoff coordinator：`sciweave.handoff-coordinator`。
- Task Agent：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`。
- Centre Workflow：`sciweave.centre-workflow.<workflow_id>`。

同一逻辑 Agent 或 Workflow 的多个实例共享同一 consumer group 并竞争消费；consumer group 不包含随机实例 ID。

`auto.offset.reset` 取 `earliest`：研究员首次启动 Agent 时要能读到注册之前已发布的历史消息，用 `latest` 会漏掉停机期间的任务。`earliest` 的安全前提是保留期未过期，且业务处理完成后才提交 offset；这两点由正文的恢复模型保证。

### 失败与恢复

- 未知消息类型、不支持的 `schema_version`、错误目标 Agent 或正式版本校验失败，写入可观察 Inbox 错误状态，不静默丢弃。
- 依赖暂时不可用、连接超时等可恢复故障进入可重试状态并采用退避；消息格式错误、未知 `schema_version`、错误目标 Agent 或正式版本校验失败进入可观察的永久 Inbox 状态，不静默丢弃。
- offset 提交失败允许消息重放；`dedupe_key` 防止重复业务执行。
- `result_unknown`、可重试失败和未绑定 Workflow 的消息由启动扫描恢复；已过期队列消息由正式 Mapping 和本地事实补偿发现。

### 序列化与 schema 版本兼容

消息体使用 **JSON（UTF-8）**，不引入 Avro 或 Protobuf，也不使用 Redpanda 自带的 Schema Registry。`shared/message-envelope/` 因此是纯 Python 数据结构加校验，不持有外部连接。

首版 `schema_version = 1`，是**整数精确匹配**，不存在次版本号。先前的「主版本」措辞作废——那种说法会让人以为存在 `1.x`。

兼容策略采用**容忍式读取**：

- `schema_version` 相等的消息一律可消费，消费方**必须忽略 payload 中的未知字段**。
- 新增字段必须是**可选**的，并在协议包中声明文档化默认值。新增必填字段等效于破坏兼容。
- 已有字段名**不得改变用途**。同名不同义比新增字段危险得多，容忍式读取完全挡不住这种情况，只能靠这条禁令。
- 只有删除字段、改变字段语义或改变必填性，才升 `schema_version`。
- 升至 `2` 是一次破坏性迁移，不是配置切换：新旧版本需要并存窗口或同步升级，由当时的消费方数量决定。

判定标准只有一条：`schema_version` 不等即视为不支持，写入可观察 Inbox 错误状态，不静默丢弃。

### 消息信封归属与依赖边界

消息信封是中央多个独立项目共用的协议代码，按 `docs/TECH_STACK.md` 的共享代码规则落在：

```text
sci-weave/centre-control/shared/message-envelope/
```

该包是**纯协议包**：只做 schema 定义、序列化、反序列化、信封构造与校验，不依赖任何 Kafka 客户端，不持有连接、不启动消费者、不含重试循环。各角色自行接入客户端：

- handoff coordinator 需要 producer（发布 `task_handoff_ready`）、consumer（消费 `dependency-notice`）与 admin（topic 保障）。
- 领域管理流程只需要 producer（发布治理事件与 `dependency-notice`）。
- Task Agent subscriber 只需要 consumer（消费 `sciweave.task-handoff.<agent_id>`）。

客户端选型：Python 侧统一使用 `confluent-kafka`（Apache 2.0，同时覆盖 producer、consumer 与 admin）。版本约束、许可证记录、锁文件与验证命令由各自引入该依赖的实现票单独登记，并按 `docs/DEPENDENCIES.md` 要求写入 `pyproject.toml` 与 `uv.lock`。

### topic 生命周期与创建权

`topic` 的创建权归**发布方**，不归订阅方。

- `sciweave.dependency-notice` 与 `sciweave.governance-events` 由中央基础设施初始化创建，属于固定 topic，创建一次后不再变更。
- `sciweave.task-handoff.<agent_id>` 由 handoff coordinator 在发布前按需幂等创建（存在即跳过），不由 Agent 侧创建。
- Task Agent subscriber 只订阅，不创建 topic。订阅时 topic 不存在，属于可观察配置错误，重试等待，不自行创建。

理由：发布方先于订阅方存在的场景必然出现——coordinator 在 Agent 注册、上线之前就可能需要发布交接。若由 Agent 侧建 topic，此时发布方要么失败，要么落到 broker 的 `auto.create.topics.enable` 自动创建路径上，分区数与副本数不受我们控制。

由此产生的约束：

- 本地验证环境的 Redpanda 必须关闭 `auto.create.topics.enable`，让「topic 不存在」暴露为明确错误而不是静默创建。
- topic 创建参数（分区数、副本数、保留期）从环境变量读取，默认值在实现票中登记；代码不硬编码。
- 单节点本地 Compose 只能使用副本数 `1`；生产副本配置仍未定，不在本票范围。

> 与 `ai4-nfty` 的关系：该票写「Agent 注册完成且具备接收任务条件时创建 topic」。本节不推翻其意图（Agent 注册后该 topic 应当存在），只补充创建动作的实际执行方是发布方。`ai4-nfty` 已由 hanjiang 关闭，本节作为本票的补充裁决记录，不回改其正文。

### dependency_kind 的首版处理口径

`dependency_kind` 取值由 `ai4-r3so` 与 `ai4-t5zl` 定义，本票只规定消息侧如何处置：

- `blocking`：按 `blocks_until` 与 `required_outputs` 判定，条件满足且执行者可用才发布 `task_handoff_ready`。
- `information`：产生通知事实与 `PendingHandoff`，但不单独触发执行。是否触发由目标任务定义决定。
- `conditional`：`activation_condition` 能自动判定时按判定结果处理；**不能判定时不得自动放行**，写入 `PendingHandoff(status=waiting, waiting_reason=activation_condition_unknown)` 并生成 `human_notification_intent`，由人工判断或补充信息。
- `alternative`：按 `alternative_group_id` 归组记录候选路径，**不允许 Agent 自行选择路线**；同组内没有可判定的激活条件时进入与 `conditional` 相同的人工等待路径。

不允许把任何 `dependency_kind` 一律当作「全部上游完成即放行」。当前 `coordinator` 的 Fake ports 实现只按上游完成事实判定，缺少 `dependency_kind`、`activation_condition`、`required_outputs` 与 `blocks_until` 字段，由后续实现票补齐。

### 根任务派发

无入边的根 TaskNode **不自动派发**。交接协调服务在任何正式版本发布时都不为无入边节点生成 `task_handoff_ready`。

根任务的首条交接只由 PO 显式调用幂等工具 `dispatch_root_task` 触发，该工具复用交接协调服务的发布端口，校验正式 Map 与 `executor_refs` 后落一条 `HandoffDispatch`。理由：根任务是 PO 的决策动作，不能因为某次无关的正式版本发布就被顺带触发。

因此「无入边」在依赖重算里是**不满足可自动派发条件**，不是「条件平凡满足」。实现上必须显式排除零入边节点，不能依赖 `all([]) == True` 的空真值。

后续为 PO 提供套件后，`dispatch_root_task` 作为该套件的一个工具入口暴露，本票只定消息侧语义。

### 重试上限与退避

`HandoffDispatch` 的重试参数默认值：

```text
max_attempts       = 5
backoff_initial    = 1s
backoff_max        = 60s
backoff_strategy   = exponential（1s, 2s, 4s, 8s, 16s，封顶 60s）
```

参数通过环境变量配置，默认值如上。`coordinator` 现有 `SCIWEAVE_COORDINATOR_MAX_ATTEMPTS` 的默认值 `3` 必须改为 `5`，`README.md` 与 `.env.example` 同步。

`attempt_count` 达到 `max_attempts` 仍未确认发布成功的 dispatch 转入 `dead`，只保留可观察记录，**不自动重放**，由人工经运维查询处理。`result_unknown` 与 `failed` 之间的区分保持不变：`result_unknown` 表示可能已发出，`failed` 表示确定未发出。

### 重复派发的去重

`HandoffDispatch` 的幂等键**不含触发 revision**：

```text
dedupe_key = mapping_domain_id + task_node_id + target_node_version_ref + message_type
```

同一个目标节点版本、同一种消息类型只派发一次。新增正式版本只改变依赖重算的输入，不构成再次派发的理由。

`ai4-zc85` 的「状态迁移校验」同时适用：`PendingHandoff` 一旦进入 `done`，后续重算不得把它退回 `waiting`。两者叠加，保证「revision 变化」和「状态回退」都不会重复派发。

### executor_refs 多值选择

`executor_refs` 可以引用协作集合，允许多个 `agent_id`。发布 `task_handoff_ready` 时的选择规则：

1. 按 `executor_refs` 声明顺序，选第一个**当前可用**的 `agent_id`。
2. 全部不可用时，不发布 `task_handoff_ready`，保留 `PendingHandoff(status=waiting)` 并生成 `human_notification_intent`。
3. 不可取「只取第一个元素」的写法——第一个离线而第二个在线时，那是误判。

`target_agent_id` 记录实际被选中的那一个，`executor_ref_snapshot` 记录完整的 `executor_refs` 快照。

### PendingHandoff 与 HandoffDispatch 状态词表

以 `coordinator` 现有实现为准，文档与之对齐：

```text
PendingHandoff.status
    waiting              等待条件满足（依赖、正式化、执行者可用性）
    ready                条件已满足，待派发
    dispatched_unknown   已发起派发但结果未知
    done                 已成功派发
    superseded           执行者转移或节点被新版本取代
    failed               不可恢复失败，转人工

HandoffDispatch.status
    created              已建记录，尚未发布
    published            发布成功
    result_unknown       发布后进程崩溃，结果未知
    failed               确定未发出，可重试
    dead                 达到重试上限，只留记录不自动重放
```

`retryable` / `pending` / `unknown` 这几个旧称不作为状态值使用。

### task_completed 的发布时点

`task_completed` 在 Task Agent Worker 把草稿写入草稿箱成功、且 ExecutionRecord 保存 `completed` 与 `draft_id` 之后立即发布，不等任何审核结论。

草稿后续被要求返修时，产生的是 `revision_of` 关联的**新一轮执行**，不是同一 ExecutionRecord 的重试。新一轮执行完成时是否再次发布 `task_completed`，取决于它是否形成了新的 `completed` 执行记录：

- 新一轮执行完成并写出新草稿：发布一条新的 `task_completed`，其 `execution_id` 与 `draft_id` 是新值。
- 同一 ExecutionRecord 不重复发布 `task_completed`。

协调器只消费 `task_completed` 解除下游依赖条件，不判断草稿是否通过审核。审核与正式化由后续 `formal_revision_published` 承担。

## 消息语义规格（2026-10-25 收口）

本节约束 Redpanda 上的主题、分区、消费者组、保留期与 offset 提交语义，作为实现票（Task Agent subscriber、Centre Agent 触发、handoff coordinator 接入）的引用契约。来源：`docs/data-flow/message-queue.md`、`docs/data-flow/message-delivery-recovery.md`、子票 ai4-nfty/ai4-zc85/ai4-2982 的结论。

### 1. 物理主题与订阅关系

四个固定物理 topic，不按 TaskNode 或 Workflow 动态创建：

| topic | 事件类型 | 消费者 |
| --- | --- | --- |
| `sciweave.dependency-notice` | `downstream_dependency_notice` | handoff coordinator（唯一主消费者） |
| `sciweave.task-handoff.<agent_id>` | `task_handoff_ready` | 目标 Task Agent subscriber（按 agent 隔离的模板） |
| `sciweave.governance-events` | `candidate_created`、`candidate_head_updated`、`formal_revision_published` | centre-workflow 的可扩展订阅者（独立消费者组） |
| `sciweave.notification-intent` | `human_notification_intent`、`task_terminal_summary` | email-service 或其他通知投递服务 |

`task-handoff` 物理 topic 使用 `sciweave.task-handoff.<agent_id>` 模板；一个 Agent 可负责多个 TaskNode，同一 Agent 的多个实例共享同一消费者组并竞争消费。topic 隔离不构成授权来源，正式 `executor_refs` 仍是 TaskNode 执行关系权威。

### 2. 分区与分区键

- 业务上每个目标 TaskNode 拥有独立逻辑频道；分区键使用目标 TaskNode 逻辑 ID 或目标版本引用。
- 同一 `task_node_id` 的消息必须落入同一分区，保证按目标有序；不同 TaskNode 可并发处理。
- 首版不按 TaskNode 动态建分区，分区数由部署配置决定（本地单节点默认 1 分区，多分区时按分区键自动路由）。

### 3. 消费者组命名与隔离

- Task Agent：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`；多实例共享该组竞争消费，重新上线继续消费未提交 offset。
- Centre Workflow：每个 Workflow 独立订阅声明与消费者组（如 `sciweave.centre-workflow.<workflow_id>`），避免一个 Workflow 消费后让另一个丢失事件。
- email-service：独立消费者组，只消费 `notification-intent`。
- handoff coordinator：`sciweave.dependency-notice` 的唯一消费者组。

### 4. offset 提交时机与幂等

- **业务完结后提交**（至少一次投递）：Task Agent 在 ExecutionRecord 到达终态（`completed`/`failed`/`cancelled` 等）后提交；coordinator 在 PendingHandoff/HandoffDispatch 持久化后提交；邮件在投递状态记录后提交。
- 崩溃重启会重放消息，重复由业务键唯一约束挡住：Task Agent 用 `(task_node_id, target_node_version_ref, trigger_revision_id)`，coordinator 用 `dedupe_key`，邮件用 `dedupe_key`。
- 不追求精确一次；不把 offset 提交与跨存储事务捆绑。

### 5. auto.offset.reset

- 新建消费者组（首次启动/注册前已有历史消息）使用 `earliest`，否则新 Agent 会漏掉注册前的历史交接。
- 已有 offset 的组不受 reset 影响，按已提交 offset 继续消费。

### 6. 保留期与过期恢复

- 本地单节点 Redpanda 保留期按部署配置（默认 7 天，可用环境变量覆盖）。
- 消息过期不构成永久事实丢失：服务依赖正式 Mapping + 未完成 `PendingHandoff`/`HandoffDispatch`/Inbox 做补偿重算，第三层恢复兜底。
- 长期离线超过保留期后，新消息照常投递；过期消息由启动扫描补偿生成。

### 7. 载荷封套与版本引用

统一信封：`event_id`、`event_type`、`schema_version`、`mapping_domain_id`、`occurred_at`、`dedupe_key`、`target`（`kind`/`id`）、`payload`。`target.kind` 表达目标类型，不作为权限来源。

- `task_handoff_ready` 必带：`target_agent_id`、`target_node_version_ref`、`source_node_version_ref`、`dependency_edge_version_ref`、`formal_revision_id`、`required_outputs`、`business_key`。
- `downstream_dependency_notice` 必带：`formal_revision_id`、源节点/目标节点/依赖边版本引用。
- `human_notification_intent`/`task_terminal_summary` 必带：`notification_kind`、收件人、`pending_handoff_id`（如有）、`source_formal_revision_id`、`target_task_node_logical_id`、`reason`、`dedupe_key`。
- subscriber 校验 `target_agent_id` 与本地 Agent 身份、`target_node_version_ref` 与正式执行关系；topic 隔离不能替代 `executor_refs` 鉴权。

### 8. 失败边界

| 场景 | 处置 |
| --- | --- |
| Redpanda/基础设施临时不可用 | 不提交 offset，等待重连重试 |
| 消息格式非法且无法重试 | 记录错误/死信，不无限阻塞分区 |
| 正式 Mapping 条件不满足 | 保存 PendingHandoff，提交 `dependency-notice` offset |
| 交接发送结果未知 | 保存 HandoffDispatch(`unknown`)，启动扫描重试 |
| Task Agent 明确失败 | ExecutionRecord=`failed`，按规则提交 `task-handoff` offset |
| 邮件投递失败 | notification intent 保持 retryable，不阻塞 Task Agent、不修改正式 Map |

### 9. 生命周期

- Agent 注册完成且具备接收任务条件时创建 `sciweave.task-handoff.<agent_id>`。
- Agent 注销不删除 topic 或 Registry 记录，只标记注销/不可用；离线保留 topic、消费者组与未消费消息。
- topic 创建/订阅/加载/启动失败不修改正式 Map，形成可观察配置错误并支持人工处理。
- 不执行自动删除 topic 的原子操作。

## Notes

**2026-10-25 规格收口并关闭（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

2026-10-25 将验收标准八项全部勾选并把「消息语义规格(2026-10-25 收口)」写入正文，正式落定主题划分(1)/分区键(2)/消费者组(3)/offset 提交(4)/auto.offset.reset(5)/保留期与恢复(6)/载荷封套(7)/失败边界(8)/生命周期(9)九个层面的实现契约。依据：`docs/data-flow/message-queue.md`、`docs/data-flow/message-delivery-recovery.md`、子票 ai4-nfty/ai4-zc85/ai4-2982 已闭合结论。现有实现可对齐：handoff coordinator(ai4-1y6q) 已落地 PendingHandoff/HandoffDispatch/三层恢复/业务键去重；Task Agent subscriber 与 Centre Agent 触发待接入真实 Redpanda 适配器。

验收依据：八项验收对应的语义均已在本票正文与关联 data-flow 文档中有确定结论，无需更多讨论输入。实现类工作（真实 Redpanda 客户端、topic 生命周期、subscriber 落地）由 ai4-z3z4/ai4-a2ba/ai4-za77 等实现票承接，不再阻塞本规格票。本票关闭，规格结论作为实现引用契约。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属并记录，不改写正文与验收标准。

**2026-10-18T15:38:23Z**

补充记录：将 `humans/dev/消息队列协作设计.md` 的现有讨论输入纳入本工单；草案目前尚未批准，以下均为待讨论方向，不代表产品语义或基础设施选型已经确定。

初始方向：
- 消息协作面向多人、多 Agent 的任务交接，不只是后台任务派发。
- TaskNode 可作为 topic，下游节点可监听前置节点消息；一个节点可以有多个监听者，所有监听者都应收到消息。
- 消息应结构化并承载进度等协作载荷；详细材料通过 Wiki 或 Buffer 链接访问，不在消息中放置大段正文。
- 端侧 Agent 可通过专用 tools 和 MCP 通知审核人；审核人使用自己的 harness 检查 Buffer 修改并通知 Project Owner。涉及多个 Proposal 或候选分支时，Central Agent 预审是独立步骤。
- 人工交接只有在接收者完成工作并通过自己的 harness 发送后续消息后才算完成；仅收到或确认通知不算完成。接收者发送后续消息前处于阻塞状态，上游节点发出交接消息后解除自身阻塞。
- 若不创建后续 TaskNode，仍应向 Project Owner 发送汇总结果。多个接收者可以分别直接向下游通知，不要求由单一负责人统一汇总。

开放问题：
- 下游节点应等待所有前置节点消息，还是按 Dependency Edge 激活条件决定。
- 消息类型如何划分（例如进度更新与完成交接），哪些类型会触发下游工作。
- 多个监听者的独立工作、阻塞状态、完成条件和分支之间如何关联。
- 人类接收者延迟或不可用时如何提醒、转交或人工解除；超时本身不能代表工作完成。
- 专用 MCP/tools 的职责，以及 Central Agent 预审如何衔接 TaskNode 消息交接。
- 载荷必填字段、消息版本、Wiki/Buffer 链接、topic 订阅范围、订阅者变更和接收者快照规则。
- 产品层消息语义与最终队列基础设施、协议、存储及部署方案的边界。

本讨论暂不包含消息队列产品、协议、数据库或云服务选型，最终载荷结构或状态机，代码实现、依赖新增和部署设计。

> 修订（2026-10-21）：其中「消息队列产品选型」已不再适用，Redpanda 已选定。其余排除项仍然有效。

**2026-10-18T15:39:58Z**

消息队列草案已纳入本工单讨论备注；相关规划变更已推送至 feature/qiyueran，当前提交 622cae7；关联 Pull Request：docs(wayfinder): expand collaboration specification map（https://gitee.com/qi-yueran/ai4science/pulls/8，目标 develop）。本工单保持开放。

**2026-10-21T14:14:43Z**

2026-10-21T22:17:00Z

范围上调，依据「Agent 以消息驱动，MCP 只负责返修」(ai4-dhpv)：消息队列原本被当作「协作通道之一」，现在成为**任务下发的唯一通道**。

对本票的影响：

- 本票从「厘清消息模型与交接语义」升级为「定义任务下发的唯一通道」。MCP 不再承担任务交付，只承担返修与观察。
- 需要覆盖的事件至少包括：上游交接就绪、根任务就绪、执行进入待接纳、返修要求、正式版本发布。
- 端侧 task-agent 与端侧 centre-agent 都主动连接中央队列订阅；出站连接即可，不做端侧入站可达。
- 「接收确认」与「阻塞解除」的语义直接决定任务能否推进，不再是可选细节。

本票仍 open。

**2026-10-21T22:56:00Z**

选型已定：**Redpanda**。依据 `docs/TECH_STACK.md` 与 `sci-weave/service/redpanda/` 的既有单节点 Compose（镜像 `redpandadata/redpanda:v24.3.7`）。

因此本票的范围收窄为在已定产品之上定义语义，需要给出：

- 主题划分：按 TaskNode 一 topic，还是按事件类型分 topic，或两者组合。
- 分区与键：用 `task_node_id` 作分区键以保证同一节点有序？这与 Gateway 的「同一 TaskNode 串行」如何对齐。
- 消费者组命名规则：端侧多个 agent 如何各自归属，避免互相抢消息。
- offset 提交时机：执行后提交（至少一次，可能重复，需要幂等）还是执行前提交（可能丢失）。
- `auto.offset.reset` 取值：研究员首次启动 agent 时要用 `earliest` 才能读到注册前的历史消息，用 `latest` 会漏。
- 保留期：Redpanda 默认 7 天，研究员长期离线后消息会被清理，是否需要调大或另设补偿机制。
- 重复投递的处理：幂等键放在消息里还是由消费者按业务键去重。

已确认的行为（2026-10-21 讨论）：研究员关机后消息留在队列；开机启动 agent 用同一消费者组可继续消费未提交 offset 之后的消息。前提是保留期未过期且 offset 在任务完成后提交。

**2026-10-22T09:30:00Z**

2026-10-22 事实记录（不改正文，本票的语义仍待讨论，依据 Project Owner「后续讨论」）。

「最小 Work Agent 实现规格」(ai4-z3z4) 已经开工，它在等本票之前只能假定三条语义，否则订阅器与预审触发都写不下去：

1. **至少一次投递**：重复投递允许出现，去重靠消费者按业务键（`task_node_id` + 触发版本标识）的唯一约束。
2. **按目标有序**：同一 `task_node_id` 的消息有序，否则「先建 queued 再领租约」会与乱序到达的消息冲突。
3. **offset 在执行完结后提交**：崩溃重启会重放，重复由业务键挡住；不追求精确一次。

这是三条**假定**，不是本票的结论。若后续讨论推翻其中任何一条，受影响的是 `ai4-z3z4` 的消息进入路径与 `ai4-a2ba` 的预审触发去抖，需要一并改。本票其余的七项语义（topic 划分、分区键、消费者组命名、`auto.offset.reset`、保留期、载荷结构、订阅者变更）仍完全开放。

**2026-10-26 开放问题结清（Frank Qi）**

上面 2026-10-21 列出的七项语义与 2026-10-18 列出的开放问题，已在本票正文与 `docs/data-flow/message-queue.md`、`docs/data-flow/message-delivery-recovery.md` 中逐条定稿，原文保留仅作历史。逐项对应：

| 原开放项 | 结论位置 |
| --- | --- |
| topic 划分 | 正文「首版消息类型」「topic 生命周期与创建权」 |
| 分区键 | 正文「Current design boundary」，`target_node_id` |
| 消费者组命名 | 正文「消费者组」 |
| offset 提交时机 | 正文「Current design boundary」，业务完成后提交 |
| `auto.offset.reset` | 正文「消费者组」与恢复模型，`earliest` |
| 保留期 | 正文「Current design boundary」，短期恢复窗口而非事实保存期限 |
| 重复投递处理 | 正文「重复派发的去重」 |
| 载荷结构与版本 | 正文「统一消息信封」，含 `dependency_edge_version_refs` |
| 订阅者变更 | `ai4-nfty` 与 `ai4-za77` 承接，本票只定协议 |

三条假定（至少一次投递、按目标有序、执行完结后提交 offset）经 2026-10-26 复核**继续成立**，已作为正式结论并入正文，不再是假定。

## Next implementation boundary

本票已定死客户端选型（`confluent-kafka`）与信封协议，但本票不含实现代码。实现票必须单独记录版本约束、许可证、锁文件和验证命令，并按 `docs/DEPENDENCIES.md` 写入各自子项目的 `pyproject.toml` 与 `uv.lock`。

已有规格与实现票继续承担各自边界：

- `ai4-p5f3`：handoff coordinator 的部署和职责边界。
- `ai4-zc85` / `ai4-1y6q`：协调核心的状态、重算、重试和恢复；`ai4-1y6q` 已完成 Fake ports 实现，不包含真实 Redpanda 适配。
- `ai4-10ja`：修复 `ai4-1y6q` 遗留的派发幂等、状态回退、执行者选择、根节点自动派发与 `dead` 状态未落地等缺陷；协议依据来自本票。
- `ai4-nfty`：Task Agent 动态订阅、Inbox、consumer group 和补偿；其真实 Redpanda subscriber 适配待实现票承接。
- `ai4-za77`：研究员 Task Agent 套件收口；真实 subscriber、启动脚本和端到端队列链路必须引用本票最终协议。

不在本票中直接实现 Redpanda producer/consumer、Task Agent subscriber 或 coordinator 的部署适配。

## Decisions so far

- [Agent 注册、Map 执行关系与消息订阅边界](ai4-0s02)：`TaskNode.executor_refs` 直接引用 Workflow Agent 的稳定 `agent_id`，是正式任务分配和消息路由依据；Registry 只登记主体、Workflow Agent 和运行实例的基本事实，不保存 TaskNode 关系，Agent 离线或注销不自动修改 Map。
- [email-service 通知意图协议与投递状态规格](ai4-f985)：首版只走受鉴权 MCP，不消费通知 topic；投递状态独立保存，邮件成败不改变领域事实。
- 首版任务下发使用 Redpanda；首版通知使用 email-service 受鉴权 MCP，不消费通知 topic。
- 任务交接使用 `sciweave.task-handoff.<agent_id>`，同一逻辑 Agent 的多个实例共享派生 consumer group。
- 消息至少一次投递，业务完成后提交 offset，重复消息按 `dedupe_key` 幂等处理。

**2026-10-26 Grill-with-docs 收敛结论（Frank Qi）**

本轮确认并回写以下决策：

- 逻辑 topic 家族与物理 topic 分离；任务交接使用 `sciweave.task-handoff.<agent_id>`，治理事件使用共享 `sciweave.governance-events`，不按 TaskNode 或 Workflow 实例动态建 topic。
- 首版移除 `sciweave.notification-intent` 队列入口，`human_notification_intent` 只通过 email-service 受鉴权 MCP 传递。
- 首版消息类型、唯一生产者、统一消息信封、核心 payload、`target_node_id` 分区键和 consumer group 命名已确定。
- 消息采用至少一次投递，业务完成后提交 offset，重复消息按 `dedupe_key` 幂等；未知类型、版本不兼容、目标错误和正式版本校验失败必须进入可观察 Inbox 状态。
- 队列保留期只提供短期离线恢复窗口；恢复依靠 consumer group、端侧 Inbox、协调记录和正式 Mapping 补偿，不新增独立死信 topic。

**2026-10-26 第二轮收敛（Frank Qi）**

> 修订：上一条「本票只定义协议，不选择或引入具体 Python Redpanda 客户端」已作废。本轮确认客户端选型属于协议可落地性的一部分，在本票定死；真实适配代码仍由实现票承接。

本轮补记：

- 消息信封落在 `sci-weave/centre-control/shared/message-envelope/`，是纯协议包，不含 Kafka 客户端、连接或重试循环。
- Python 客户端统一为 `confluent-kafka`（Apache 2.0，覆盖 producer、consumer、admin）。版本、许可证、锁文件和验证命令由各自实现票登记。
- `dependency_kind` 四种取值分别处置：`blocking` 按条件放行；`information` 只产生通知事实；`conditional` 条件不可判定时进人工等待，不得自动放行；`alternative` 按组记录，不允许 Agent 自选路线。
- `HandoffDispatch` 重试默认 `max_attempts=5`、指数退避 1s 起、封顶 60s；达上限转 `dead`，记录保留但不自动重放。
- `task_completed` 在草稿写入成功且 ExecutionRecord 保存 `completed` 与 `draft_id` 后立即发布；同一 ExecutionRecord 不重复发布，返修产生新执行时发布新的 `task_completed`。

**2026-10-26 第三轮收敛：对照 coordinator 实现复核（Frank Qi）**

本轮把 `sci-weave/centre-control/coordinator` 当沙箱跑了一遍，用实测结果反查协议缺口。结论按「协议层修正」与「实现层缺陷」分开。

协议层修正，已写入正文：

- 无入边根节点不自动派发，只由 PO 的 `dispatch_root_task` 触发；不得依赖 `all([]) == True` 的空真值。
- `HandoffDispatch` 幂等键去掉 `trigger_revision_id`，改为 `mapping_domain_id + task_node_id + target_node_version_ref + message_type`；叠加 `ai4-zc85` 的状态迁移校验，`done` 不得退回 `waiting`。
- `executor_refs` 多值时按声明顺序取第一个可用 Agent；全部不可用转人工。禁止「只取第一个元素」。
- `max_attempts` 默认统一为 `5`；`coordinator` 现有默认 `3` 与 `.env.example`、`README.md` 一并改。
- 状态词表以现有实现为准：`PendingHandoff` 用 `waiting/ready/dispatched_unknown/done/superseded/failed`，`HandoffDispatch` 用 `created/published/result_unknown/failed/dead`。
- `task_handoff_ready` 载荷补 `dependency_edge_version_refs`，与正文第 45 行「精确引用 DependencyEdge 版本」的要求对齐。

实测证据（同一进程内用 Fake ports 复现）：

```text
同一节点版本、三个 revision     → 派发 3 次（应 1 次）
done 后再次重算                 → 退回 waiting
executor_refs=(a1,a2)、仅 a2 在线 → 判定无可用执行者（应派发给 a2）
无入边根节点 + 任意正式版本发布   → 自动派发 1 次（应 0 次）
DISPATCH_DEAD                  → 全仓库只被 import，从未写入
recipients                     → 传 mapping_domain_id，非 principal_id
```

实现层缺陷不在本票修改，由新建的实现票承接：重复派发、状态回退、多执行者选择、根节点自动派发、`dead` 状态未落地、人工通知收件人取值错误、`dependency_kind` 与激活条件字段缺失、快照错误码路径不一致。

**2026-10-26 第四轮收敛：人工通知收件人（Frank Qi）**

缺陷 6「收件人传成 `mapping_domain_id`」查下去，根因不是变量写错，而是「该发给谁」这个事实从未被定义。本轮定死：

- 一条通知只有一个收件人，是**需要动手的那个人**，不是抄送名单。
- 收件人角色由 `notification_kind` 决定，调用方不得自行挑选。三种「执行者不可用」拆成 `workflow_binding_required`（`executor_refs` 为空）、`workflow_load_failed`（指向未登记 `agent_id`）、`agent_unavailable`（已注销、无可用实例或只配置人工处理），前三者指向该节点 TaskNode Owner；`task_terminal_summary` 指向项目负责人。
- `task_owner_id` 是 TaskNode 文档必填字段，缺失表示数据损坏。此时不猜收件人、不生成通知，保留 `PendingHandoff(status=waiting)` 并记录 `recipient_unresolved:task_owner_id_missing`。
- 项目负责人身份不新建名册，取自 `formal_mapping_revision.published_by`——它是最近一次批准该域正式版本的人，且落库前已通过 `is_project_owner` 校验。字段名用 `latest_published_by`，不叫 `project_owner_id`，因为它回答的是「最近批准者」而非「被任命的负责人」。详见 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)。
- `task_owner_id` 本来就在 TaskNode 文档中，由快照适配器直接投影，research-map 侧零改动；`published_by` 在 SQLite 的 `formal_mapping_revision` 表中，需要 `get_formal_mapping_at_revision` 把它加进返回，属于 research-map 侧改动。
- 发送前由协调服务经 Registry 校验 `principal_id` 存在且 `active`；不通过则不建 dispatch、记错误、保持 `waiting`。Registry 不可用时 fail-open 照发——宁可发一条可能失败的邮件，也不能因为校验渠道故障而完全不发。

映射表落在 `docs/data-flow/message-delivery-recovery.md`，`GLOSSARY.md` 的「通知收件人」只补一句「角色由通知类型决定」，不承载映射表。

**第四轮后续：快照适配器（Frank Qi）**

`coordinator` 至今没有任何真实适配器：`src/main.py` 只读配置、开 SQLite、打日志、关连接，四个 Port 全是 Protocol。原因是四个口子各自卡在不同上游，而「接入」这一步从未被立成票。

快照适配器是其中唯一上游已清零的一个：`ai4-2982` 已关闭，`get_formal_mapping_at_revision` 已实现并通过 115 项测试，返回的 `documents` 是原始 TerminusDB 文档。它不需要 Redpanda、不需要信封包、不需要 email-service，而且是让收件人规则真正生效的前提——没有它，`TaskNodeDoc.task_owner_id` 永远是 `None`。

适配器范围取最小投影：只产出 `DependencyEdgeDoc` 现有字段，把嵌套的 `source_node_version_ref` / `target_node_version_ref` 拍平；`dependency_kind`、`activation_condition`、`required_outputs`、`blocks_until` 暂不投影，代码留显式注释指向后续票，不得静默丢弃。节点投影 `task_node_id`、`version_id`、`executor_refs`、`task_owner_id`。

其余三个适配器继续等待：Registry 侧等 `ai4-1kls`（open），消息发布侧等信封包，通知侧等本轮的收件人规则（已定，但依赖快照适配器提供 `task_owner_id`）。

**2026-10-26 第五轮收敛：序列化与信封包归属（Frank Qi）**

本轮补掉三个会让「接信封包的人被迫自己拍板协议」的缺口：

- 序列化定为 **JSON（UTF-8）**，不引 Avro、Protobuf，也不使用 Redpanda 自带的 Schema Registry。首版只有三类消息、两个生产者，消费方全是自家 Python 服务；Avro 的紧凑与强演进在这个规模换不回它的负担——多一个序列化依赖、多一套注册逻辑、开发机上多一个必须活着的服务。代价明确：将来换 Avro 是破坏性迁移，不是配置切换。
- `schema_version` 是**整数精确匹配**，不存在次版本。「主版本」这个措辞作废，它会让人以为有 `1.x`。
- 兼容策略取**容忍式读取**：同版本一律可消费、消费方必须忽略未知字段、新增字段必须可选且声明文档化默认值、已有字段名不得改用途、只有删字段/改语义/改必填性才升版本。两条红线是「新字段必须可选」和「字段名不得改用途」——后者尤其重要，容忍式读取完全挡不住同名不同义。
- 信封包 `shared/message-envelope/` 至今没有承接票。`sci-weave/centre-control/shared/` 下只有 `audit-trail`，而全仓库只有三张票提到过这个路径。由新票 [实现消息信封纯协议包](ai4-3zxu.md) 承接，不并入任何使用方的适配器票：它是中央多项目共用包，让第一个使用方替所有使用方定义协议是错的。

## Resolution

本票作为协议决策分支关闭。19 条验收全部勾选，五轮收敛覆盖：首批消息类型与 topic、统一信封与载荷、消费者组与偏移语义、重试上限与退避、去重、状态词表、根任务派发、executor_refs 多值选择、topic 生命周期、人工通知收件人、序列化与版本兼容。

协议层面的未决项为零。以下工作已全部拆为独立票，不在本票承接：

- [修复 handoff coordinator 派发幂等与执行者选择缺陷](ai4-10ja.md)：七个已复现的实现缺陷。
- [handoff coordinator 快照适配器接入 research-map 正式快照](ai4-edrp.md)：首个真实适配器。
- [实现消息信封纯协议包](ai4-3zxu.md)：`shared/message-envelope/`。
- [get_formal_mapping_at_revision 返回 published_by](ai4-2raq.md)：收件人规则的数据前提。

本票的 Decisions so far 需由 `ai4-xup8` 地图 owner 转载索引，见下方待办。

## 待地图 owner 转载

`ai4-xup8` 的 Decisions so far 只由该地图 assignee（hanjiang）更新。以下是建议转载的一行：

```markdown
- [消息队列协作模型分支](ai4-te1v.md)：三类物理 topic（`dependency-notice`、`task-handoff.<agent_id>`、`governance-events`）+ 统一信封；`confluent-kafka` 客户端、JSON 序列化、`schema_version` 整数精确匹配与容忍式读取；首版无 `notification-intent` topic，人工通知走 email-service MCP。
```
