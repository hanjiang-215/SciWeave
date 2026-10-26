---
id: ai4-csyj
status: closed
deps: []
links: [ai4-dhpv]
created: 2026-10-19T01:14:45Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-kpvp
tags: [wayfinder:grilling]
---
# TaskNode 交接消息发布与下游触发流程

## Question
明确领域正式版本发布后，沿 TaskNode 与 Dependency Edge 向下游负责人或端侧 Task Agent 发布交接消息的完整流程。需要决定交接消息的触发条件、消息载荷、接收者分发、依赖激活、重复投递、失败重试、下游确认与阻塞解除语义。该票不讨论端侧 agent 如何订阅，也不选择具体消息队列产品。

> 修订（2026-10-21）：触发条件由「任务完成且审核通过」改为「领域正式版本发布」。端侧自持后中央看不到执行状态机，依据工单「Task Agent 改由研究员端侧自持」。

> 修订（2026-10-26）：**范围收窄**。原验收的七项里，发布前置条件、消息结构、沿依赖边路由、投递状态、重复与失败恢复五项已由 `ai4-te1v` 完整覆盖并关闭。本票只保留 `ai4-te1v` 未覆盖的两项：**接收确认**与**下游任务解除阻塞规则**。其余五项不再在本票重复讨论。

## Acceptance Criteria

只裁决两件事：

- [x] **接收确认**：下游收到 `task_handoff_ready` 后是否、以及如何回执；回执与业务事实的关系；无回执时上游如何判定。
- [x] **下游解除阻塞**：什么事件才算下游「已可推进」，`task_handoff_ready` 送达本身够不够，以及上游自身的阻塞在何时解除。

## Resolution（2026-10-26）

### 接收确认：不新增回执消息，回执由 ExecutionRecord 创建 + offset 提交表达

- **不引入独立 ACK/回执消息类型。** `task_handoff_ready` 采用至少一次投递，端侧收到后在一个 SQLite 事务里创建 `queued` 执行记录（`trigger=queue`）即视为「已开始受理」；无单独 ACK 消息。
- **业务完成确认是 `task_completed`，不是回执。** 协调器（handoff coordinator）只消费 `task_completed` 解除下游依赖条件，不依赖回执判定任务是否真正完成。草稿是否通过审核由后续 `formal_revision_published` 承担，均不入本票语义。
- **无回执时的判定由 offset 与三层恢复兜底，不靠上游超时等待。** Agent 崩在启动阶段 → 该条 `task_handoff_ready` offset 未提交 → 重放 → 业务键唯一约束挡住第二次执行，不产生第二轮；消息过期则由正式 Mapping 补偿重算。与「人工交接：仅收到或确认通知不算完成」的既有结论对齐——机器侧同理，收到消息只是受理开始，不是完成。
- 失败处置：Task Agent 明确失败 → `ExecutionRecord=failed`，按失败规则提交 `task-handoff` offset，协调器不重发（重试由端侧租赁与恢复路径承担，不依赖消息回执）。

### 下游解除阻塞：`task_handoff_ready` 送达只是受理前提，不是「已可推进」

- **对下游 Agent**：「已可推进」= 收到消息并以业务键成功创建 `queued` 执行记录，随即可被拉起的 Worker 领取租约执行。消息到达本身只解除「该节点可开工」的前置，不解除执行中状态。
- **对协调器**：上游任务节点自身的阻塞在**正式版本发布时已解除**（`formal_revision_published` 触发依赖重算，条件满足即对下游发 `task_handoff_ready`）；`PendingHandoff` 等待态在派发成功后关闭。
- **边界确认**：存在一个人工节点在链路的场景下，「已可推进」仍以该节点完成工作并提交后续消息为准（沿用 2026-10-19 前沿结论）；机器节点则以上述 ExecutionRecord 语义为准。本裁决不改变 `ai4-te1v` 的 `task_completed` 消费边界，也不为 `ai4-za77` 增加新的订阅判定负担——端侧判断「已可推进」只需「业务键去重成功」这一个事实。

## Notes

**2026-10-26 收口（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

依据 `ai4-te1v`（2026-10-25 收口）与 `ai4-zc85`/`ai4-nfty`/`ai4-1y6q` 契约，把剩余的「接收确认」与「下游解除阻塞」两项裁决写入 Resolution 并关闭本票。要点：

- 不新增回执消息类型；受理以业务键成功创建 `queued` ExecutionRecord 为准，完成以 `task_completed` 为准，offset 提交与三层恢复兜底无回执场景。
- 下游「已可推进」= 业务键去重成功创建执行记录；上游阻塞在正式版本发布时已解除。

本票 `deps` 为空，`links` 保持 `ai4-dhpv`。正文中 2026-10-19 起的历次讨论结论保留作过程记录，裁决结论统一落于 Resolution。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属并记录，不改写正文与验收标准。

**2026-10-19T05:47:44Z**

Wayfinder 前沿结论（2026-10-19）：与端侧 Agent 的协作通道保持分离。Owner 的补充、返修、重试、暂停、取消和 Human Input 通过 A2A Gateway；上游审核通过后的单次 TaskNode 交接通过消息队列和上游收集器。A2A 可向 Owner 返回实时最终文字回复或 INPUT_REQUIRED 状态；上游自动执行完成后，结果写入 Buffer/Execution Record，并只向该 TaskNode Owner 发送一次邮件提醒，邮件不承载任务事实或审核决定。每个 TaskNode 至少有一名 Owner；上游交接只有在必要消息收齐且 Dependency Edge 激活后才触发下游执行。

**2026-10-19T20:19:00Z**

修订（2026-10-19）：上一条中“Owner ... 通过 A2A Gateway”已作废。Owner 通道改为 MCP（Streamable HTTP），因为主流 harness 均未内置 A2A 客户端；Human Input 改由 `query_execution` 返回 `waiting` 与问题文本表达，不再使用 A2A `INPUT_REQUIRED`。

本票的实质结论不变，且只涉及上游一侧：**上游 TaskNode 审核通过后的单次交接通过消息队列和上游收集器，与 Owner 通道物理隔离**。这条不受协议修订影响。

**2026-10-21T13:08:28Z**

2026-10-21T21:11:00Z

触发点变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：task-agent 跑在研究员自己的电脑上，中央看不到它的执行状态机。因此下游交接不能挂在「执行完成 → 节点负责人接纳 → 发交接」上。

新触发点：领域正式版本发布。链路为 草稿提交 → 一审通过 → 候选分支 → Project Owner 批准 → 正式版本发布 → 沿 Dependency Edge 发出交接消息。

对本票的影响：

- 交接消息的发布前置条件从「执行结果被接纳」改为「正式版本已发布」，并绑定到确切的正式版本标识。
- 交接载荷需要携带触发它的正式版本标识，而不是执行记录标识。
- 「执行结果接纳」相关语义从本票移除，属于端侧 agent 与节点负责人之间的事，不进入中央。
- 端侧 agent 通过主动连接消息队列订阅自己负责的 TaskNode，这一点与本票的发布方向正交：本票只定义发布，不定义订阅方式。

本票仍 open，正文修订随后进行。

**2026-10-26 范围收窄（Frank Qi）**

`ai4-te1v` 收敛关闭后逐项对照，原验收的七项里五项已被完整覆盖：

| 原验收项 | 现由谁覆盖 |
| --- | --- |
| 发布前置条件（正式版本已发布） | `ai4-te1v`「首版消息类型」「task_completed 的发布时点」 |
| 消息结构（含触发的正式版本标识） | `ai4-te1v`「统一消息信封」，含 `trigger_revision_id` 与 `dependency_edge_version_refs` |
| 沿依赖边的路由与多接收者处理 | `ai4-te1v`「首版消息类型」与 `target_node_id` 分区键；每个目标节点一条交接，不存在多接收者 |
| 投递状态 | `ai4-te1v`「PendingHandoff 与 HandoffDispatch 状态词表」 |
| 重复与失败恢复 | `ai4-te1v`「重复派发的去重」「重试上限与退避」 |

剩下两项确实是 `ai4-te1v` 没定的，而且都属于**交接流程**而非消息协议：

- **接收确认**：2026-10-19 的早期结论写过「人工交接只有在接收者完成工作并通过自己的 harness 发送后续消息后才算完成；仅收到或确认通知不算完成」，但那条讲的是人工交接，没回答机器侧 Task Agent 收到 `task_handoff_ready` 后要不要回执。
- **下游解除阻塞**：`task_handoff_ready` 送达本身够不够？如果够，Agent 崩在启动阶段上游永远不知道；如果不够，回执超时如何处置、是否重发。

这两个问题不解决，`ai4-za77`（Task Agent 套件）的 subscriber 就缺一块判定依据。
