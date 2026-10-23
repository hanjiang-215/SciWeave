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

形成可交给后续实现规划的消息协作领域规格，至少明确 topic/订阅、消息类型与载荷边界、接收者交接/阻塞完成语义、前置任务条件及失败/超时处理；具体基础设施选型另行决策。

> 修订（2026-10-21）：「具体基础设施选型另行决策」已完成，Redpanda 已定，见 `docs/TECH_STACK.md`。本票的验收改为在其之上定义主题、分区、消费者组、保留期与 offset 提交语义。

## Current design boundary

以下内容已作为本票继续讨论的工作基线，交接协调服务的最终归属由子票「交接协调服务的职责、存储边界与 centre-control 部署形态」裁决：

- 业务上按目标 TaskNode 形成逻辑消息频道；不要求 Agent 从上游消息中自行过滤任务。
- 物理上使用四个固定 topic：`sciweave.dependency-notice`、`sciweave.task-handoff`、`sciweave.governance-events`、`sciweave.notification-intent`，不为每个 TaskNode 或每个 Workflow 动态创建 Redpanda topic。
- `dependency-notice` 的主消费者是交接协调服务，负责读取正式 Mapping、重算依赖、维护 `PendingHandoff` 和 `HandoffDispatch`，不能直接创建 Task Agent 的 `ExecutionRecord`。
- `task-workflow` 接收 `task_handoff_ready` 并创建 Task Agent 执行；任务交接物理 topic 使用 `sciweave.task-handoff.<agent_id>` 模板，不按 TaskNode 动态创建；`centre-workflow` 接收可扩展的治理事件订阅；`email-service` 只接收 `human_notification_intent` 并投递人工通知。
- 当前 Centre Agent 是 `centre-workflow` 的一个预审 Workflow，后续可增加其他中央 Workflow；每个 Workflow 使用独立订阅声明和消费者组。
- `TaskNode.executor_refs` 决定 Task Agent 执行关系；Registry 只提供身份和实例登记事实，不授予权限。
- 消息交接必须精确引用源节点版本、目标节点版本、DependencyEdge 版本和正式 Mapping 版本；目标节点逻辑 ID或目标版本引用作为路由/分区键。
- 服务启动时恢复分为三层：同一消费者组继续消费未提交 offset，扫描未完成的 `PendingHandoff`/`HandoffDispatch`，并依据正式 Mapping 做消息过期后的补偿重算。
- `centre-agents` 是 Centre Agent 预审服务，不承担全局依赖重算；邮件服务不判断是否可以执行。
- PO 的候选裁决和根任务第一条消息均通过最高权限领域 MCP 完成；根任务使用幂等 `dispatch_root_task`，候选不支持 `defer`，返修必须指定负责人。

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

## Not yet specified

- [交接协调服务的职责、存储边界与 centre-control 部署形态](ai4-p5f3)：明确交接协调服务的中央部署、等待事实、派发恢复和多目标事件边界。
- [Research Mapping 正式快照查询接口与交接协调服务访问边界](ai4-2982)：明确交接协调服务如何通过稳定领域接口读取正式 Mapping，避免直连领域存储。
- [研究员 Task Agent 动态订阅 task-workflow 交接消息](ai4-nfty)：明确新建 Workflow 后端侧 Agent 如何根据正式 `executor_refs` 发现、订阅和恢复任务交接。
- [email-service 通知意图协议与投递状态规格](ai4-f985)：定义邮件 MCP 的输入、投递状态和失败边界，完成后才进入服务实现。
- [handoff coordinator 依赖重算与派发恢复规格](ai4-zc85)：定义协调核心的输入、输出、等待状态和恢复契约，完成后才进入服务实现。
