---
id: ai4-te1v
status: open
deps: []
links: []
created: 2026-10-18T15:18:52Z
type: epic
priority: 1
assignee: Frank Qi
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
- [x] 明确 `HandoffDispatch` 的重试上限与退避参数。
- [x] 明确 `task_completed` 的发布时点与返修后是否重发的规则。

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
- `centre-agents` 是 Centre Workflow 的预审实现，不承担全局依赖重算；PO 的候选裁决和根任务分派通过最高权限领域 MCP 完成，根任务使用幂等 `dispatch_root_task`。

### 首版消息类型

- `sciweave.dependency-notice`：`formal_revision_published`、`task_completed`。
- `sciweave.task-handoff.<agent_id>`：`task_handoff_ready`。
- `sciweave.governance-events`：`candidate_created`、`candidate_head_updated`、`formal_revision_published`。
- `human_notification_intent`、`task_terminal_summary` 不进入首版 Redpanda；`task_failed` 不触发下游完成，保存在 Task Agent 执行事实中；`root_task_dispatched` 不作为额外事件，根任务直接产生 `task_handoff_ready`。

### 统一消息信封

所有 Redpanda 业务消息使用统一信封，业务字段放在 `payload`：

- `message_id`：一次发布消息的唯一标识。
- `message_type`：消息类型。
- `schema_version`：消息 schema 主版本，首版为 `1`。
- `dedupe_key`：业务幂等键，重试发布时保持不变。
- `occurred_at`、`published_at`：事件发生和发布的时间。
- `producer`：生产服务及可选实例标识。
- `routing`：分区键及任务交接时的 `target_agent_id`。
- `payload`：业务载荷。

`task_handoff_ready` 的载荷至少包含 `target_agent_id`、`target_node_id`、`target_node_version_ref`、`mapping_domain_id`、`pending_handoff_id`、`trigger_revision_id`、`upstream_source_refs` 和 `executor_ref_snapshot`。`executor_ref_snapshot` 仅用于审计，不能替代当前正式 Map 校验。

`task_completed` 的载荷至少包含 `mapping_domain_id`、`task_node_id`、`completed_version_ref`、`execution_id`、`draft_id`、`completed_at` 和 `result_ref`；只有草稿箱写入成功且 ExecutionRecord 保存 `completed` 与 `draft_id` 后才发布。

### 消息生产者与消费者

- `formal_revision_published` 由领域正式化流程生产；handoff coordinator 与 Centre Workflow 按各自 consumer group 消费，不由 PO、Task Agent 或 coordinator 伪造。
- `task_completed` 由 Task Agent Worker 在 ExecutionRecord 保存 `completed` 且草稿箱写入成功后生产；handoff coordinator 消费。邮件发送成功、Worker 进入 `waiting`、失败或取消均不产生该事件。
- `task_handoff_ready` 由 handoff coordinator 唯一生产；根任务 `dispatch_root_task` 复用同一发布端口。Task Agent 和 Centre Agent 不得直接发布。
- `candidate_created`、`candidate_head_updated` 由候选领域管理流程生产，由 Centre Workflow 消费；Centre Agent 不生产治理事件。
- 首版治理事件的具体生产调用点必须由领域管理实现票保证与相应领域事实写入一致；本票不规定跨服务原子事务实现。

### 消费者组

- handoff coordinator：`sciweave.handoff-coordinator`。
- Task Agent：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`。
- Centre Workflow：`sciweave.centre-workflow.<workflow_id>`。

同一逻辑 Agent 或 Workflow 的多个实例共享同一 consumer group 并竞争消费；consumer group 不包含随机实例 ID。

### 失败与恢复

- 未知消息类型、不支持的主版本、错误目标 Agent 或正式版本校验失败，写入可观察 Inbox 错误状态，不静默丢弃。
- 依赖暂时不可用、连接超时等可恢复故障进入可重试状态并采用退避；消息格式错误、未知主版本、错误目标 Agent 或正式版本校验失败进入可观察的永久 Inbox 状态，不静默丢弃。
- offset 提交失败允许消息重放；`dedupe_key` 防止重复业务执行。
- `result_unknown`、可重试失败和未绑定 Workflow 的消息由启动扫描恢复；已过期队列消息由正式 Mapping 和本地事实补偿发现。

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

### dependency_kind 的首版处理口径

`dependency_kind` 取值由 `ai4-r3so` 与 `ai4-t5zl` 定义，本票只规定消息侧如何处置：

- `blocking`：按 `blocks_until` 与 `required_outputs` 判定，条件满足且执行者可用才发布 `task_handoff_ready`。
- `information`：产生通知事实与 `PendingHandoff`，但不单独触发执行。是否触发由目标任务定义决定。
- `conditional`：`activation_condition` 能自动判定时按判定结果处理；**不能判定时不得自动放行**，写入 `PendingHandoff(status=waiting, waiting_reason=activation_condition_unknown)` 并生成 `human_notification_intent`，由人工判断或补充信息。
- `alternative`：按 `alternative_group_id` 归组记录候选路径，**不允许 Agent 自行选择路线**；同组内没有可判定的激活条件时进入与 `conditional` 相同的人工等待路径。

不允许把任何 `dependency_kind` 一律当作「全部上游完成即放行」。当前 `coordinator` 的 Fake ports 实现只按上游完成事实判定，缺少 `dependency_kind`、`activation_condition`、`required_outputs` 与 `blocks_until` 字段，由后续实现票补齐。

### 重试上限与退避

`HandoffDispatch` 的重试参数默认值：

```text
max_attempts       = 5
backoff_initial    = 1s
backoff_max        = 60s
backoff_strategy   = exponential（1s, 2s, 4s, 8s, 16s，封顶 60s）
```

参数通过环境变量配置，默认值如上。`attempt_count` 达到 `max_attempts` 仍未确认发布成功的 dispatch 转入 `dead`，只保留可观察记录，**不自动重放**，由人工经运维查询处理。`result_unknown` 与 `failed` 之间的区分保持不变：`result_unknown` 表示可能已发出，`failed` 表示确定未发出。

### task_completed 的发布时点

`task_completed` 在 Task Agent Worker 把草稿写入草稿箱成功、且 ExecutionRecord 保存 `completed` 与 `draft_id` 之后立即发布，不等任何审核结论。

草稿后续被要求返修时，产生的是 `revision_of` 关联的**新一轮执行**，不是同一 ExecutionRecord 的重试。新一轮执行完成时是否再次发布 `task_completed`，取决于它是否形成了新的 `completed` 执行记录：

- 新一轮执行完成并写出新草稿：发布一条新的 `task_completed`，其 `execution_id` 与 `draft_id` 是新值。
- 同一 ExecutionRecord 不重复发布 `task_completed`。

协调器只消费 `task_completed` 解除下游依赖条件，不判断草稿是否通过审核。审核与正式化由后续 `formal_revision_published` 承担。

## Notes

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

## Decisions so far

- [Agent 注册、Map 执行关系与消息订阅边界](ai4-0s02)：`TaskNode.executor_refs` 直接引用 Workflow Agent 的稳定 `agent_id`，是正式任务分配和消息路由依据；Registry 只登记主体、Workflow Agent 和运行实例的基本事实，不保存 TaskNode 关系，Agent 离线或注销不自动修改 Map。
- [email-service 通知意图协议与投递状态规格](ai4-f985)：首版只走受鉴权 MCP，不消费通知 topic；投递状态独立保存，邮件成败不改变领域事实。实现票不再受这张规格票阻塞。

## Next implementation boundary

本票完成消息语义收敛后，后续实现不得直接假定具体 Python Redpanda 客户端。实现票必须单独记录客户端选型、版本约束、许可证、锁文件和验证命令。

已有规格与实现票继续承担各自边界：

- `ai4-p5f3`：handoff coordinator 的部署和职责边界。
- `ai4-zc85` / `ai4-1y6q`：协调核心的状态、重算、重试和恢复；`ai4-1y6q` 已完成 Fake ports 实现，不包含真实 Redpanda 适配。
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
