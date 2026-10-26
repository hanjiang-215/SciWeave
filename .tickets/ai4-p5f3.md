---
id: ai4-p5f3
status: closed
deps: []
links: []
created: 2026-10-23T11:28:01Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-te1v
tags: [wayfinder:grilling, centre-control, message-queue, handoff]
---
# 交接协调服务的职责、存储边界与 centre-control 部署形态

明确消息队列中 dependency-notice 的主消费者、PendingHandoff 的事实归属、task_handoff_ready 的生成边界，以及交接协调服务在 sci-weave/centre-control 中的独立部署形态。该票不实现服务，只形成可交给实现规划的架构决策。

## Design

需要裁决：

1. 是否新增 `sci-weave/centre-control/handoff-coordinator/` 独立 Python 子项目；
2. 为什么不由 `centre-agents` 或 `research-map` 承担；
3. `dependency-notice` 的消费、重算、幂等和补偿边界；
4. `PendingHandoff` 的存储权威和字段；
5. Research Mapping、Registry、Redpanda、通知服务之间的接口；
6. `executor_refs` 已配置但 Agent 离线、未登记或无实例时的处理；
7. `task_handoff_ready` 与 `human_notification_intent` 的发布条件；
8. 失败、重试、死信、offset 和审计边界。

## 当前决策基线

- `task-workflow`、`centre-workflow`、`email-service` 不是同一种交接消费者，不把它们都建模成 `task_handoff_ready`。
- 当前 Centre Agent 是 `centre-workflow` 的一个预审 Workflow，订阅候选创建、候选头更新和正式版本发布事件；后续中央 Workflow 通过独立订阅声明和消费者组扩展。
- 服务启动恢复采用三层模型：同一消费者组继续消费未提交 offset；扫描未完成的 `PendingHandoff` 和 `HandoffDispatch`；消息过期后依据正式 Mapping 补偿重算。
- `HandoffDispatch` 覆盖“事件发送结果未知”的崩溃窗口，重复发布由 `dedupe_key` 和下游幂等共同保护。
- 详细消息目标类型、Centre Workflow 可扩展订阅和启动恢复流程记录在 [`消息交接恢复与多目标订阅`](../docs/data-flow/message-delivery-recovery.md)。
- 已接受新增独立交接协调服务；`PendingHandoff` 与 `HandoffDispatch` 由该服务的持久化边界负责，Task Agent、Centre Agent 和邮件服务分别只保存自己的执行或投递事实。
- Research Mapping 访问方式尚未收敛，已拆为决策票「Research Mapping 正式快照查询接口与交接协调服务访问边界」；在该接口确定前，交接协调服务不能进入实现规划。
- 启动恢复和 Centre Workflow 可扩展订阅已形成基线；研究员端新建 `task-workflow` 后如何发现和订阅 `task_handoff_ready`，另由「研究员 Task Agent 动态订阅 task-workflow 交接消息」收敛。
- 候选决策不支持 `defer`：PO 必须选择 `formalize`、`request_revision` 或 `reject`。`request_revision` 必须指定唯一 `repair_owner_id`，返修由负责人自己的 Task Agent 完成，Centre Agent 不负责返修。
- 混合候选不可行时，PO 可以指派负责人组织返修，也可以通过高权限 PO MCP 创建新的混合候选；正式版本不可原地修改，Mapping 与 Wiki 仍分别治理。
- 无后续 TaskNode 时发送 `task_terminal_summary` 通知 PO；PO 通过 MCP 创建后续任务/依赖候选，不直接操作队列。
- 已新增 email-service spec；首版唯一入口是受鉴权的 MCP `send_notification`，不消费 Redpanda notification topic；统一公共邮箱发件，调用方提交主题、正文、notification_kind、收件人和稳定关联引用；通知投递不修改业务事实。
- [email-service 通知意图协议与投递状态规格](ai4-f985.md) 已关闭。邮件 MCP 的协议不再是未决项；[实现 email-service 通知意图 MCP 与投递状态](ai4-m1d1.md) 可以开工，不拆更多决策票。真实 Registry 适配不在这张实现票里。

## Acceptance Criteria

改写说明（2026-10-26）：原为 13 条普通列表项，从未有过勾选动作，导致票面看起来「还在讨论」而实际早已收敛。改为复选框并逐条核对，依据写在各条之后。

- [x] 明确交接协调服务是否作为 centre-control 下独立部署角色，以及与 centre-agents、research-map 的边界
  - 依据：`sci-weave/centre-control/coordinator/README.md`「职责边界」；`ai4-2982` 已关闭，查询走端口、不直连。
- [x] 明确 `task-workflow`、可扩展的 `centre-workflow`、`email-service` 三类目标的事件语义、订阅和消费者组
  - 依据：[`message-delivery-recovery.md`](../docs/data-flow/message-delivery-recovery.md)「目标类型不是同一种交接语义」三小节。
- [x] 明确 `dependency-notice` 的主消费者、`task_handoff_ready` 的唯一生成者和各目标 topic 的消费关系
  - 依据：`ai4-te1v`「首版消息类型」的唯一生产者表。
- [x] 明确 PendingHandoff 与 HandoffDispatch 的权威存储、生命周期、幂等键和补偿重算触发
  - 依据：`ai4-te1v`「PendingHandoff 与 HandoffDispatch 状态词表」「重复派发的去重」；恢复文档第二、三层。
- [x] 明确 executor_refs、Registry 登记、Agent 实例可用性三者的关系，不把 Registry 当授权源
  - 依据：`ai4-te1v`「executor_refs 多值选择」——按声明顺序取第一个可用者，全部不可用转人工。
- [x] 明确 human_notification_intent/通知服务的接口边界，邮件成功不等于任务完成
  - 依据：`ai4-f985` 已关闭的 email-service 规格；`ai4-te1v`「人工通知的收件人」。
- [x] 明确候选决策不支持 `defer`，`request_revision` 必须指定唯一 `repair_owner_id`，Centre Agent 不承担返修
  - 依据：恢复文档「候选裁决不支持 defer」；本票「当前决策基线」第 9 条。
- [x] 明确混合候选不可行、PO 直接创建新混合候选、Mapping/Wiki 独立治理和无后续 TaskNode 通知 PO 的流程
  - 依据：本票「当前决策基线」第 10 条；[`centre-agent.md`](../docs/data-flow/centre-agent.md) 混合候选行。
- [x] 明确 PO 高权限 MCP 不直接操作队列或领域存储，根任务通过幂等分派工具生成任务交接
  - 依据：恢复文档「PO 操作与根任务消息」。**接口契约已定，`dispatch_root_task` 尚无实现**，由 `ai4-10ja` 承接。
- [x] 明确正式版本当前无后继时先保存待推进检测，确认无后继后通知 PO；后续新后继正式化后自动生成任务交接
  - 依据：恢复文档「当前没有后继 TaskNode」；后继正式化后由快照重算路径自动生成交接。
- [x] 明确队列基础设施失败、非法消息、领域条件不满足、派发结果未知和 Worker 业务失败的不同处置
  - 依据：恢复文档「失败边界」五种情形逐条对应。
- [x] 明确服务启动恢复未提交 offset、未完成协调记录和消息过期补偿扫描三层边界
  - 依据：恢复文档第一、二、三层。
- [x] 形成可供实现票引用的部署、配置、依赖和验证边界
  - 依据：`coordinator/README.md`「配置」「验证」两节、`.env.example`、`uv.lock`。
  - 已知偏差：README 与 `.env.example` 的 `SCIWEAVE_COORDINATOR_MAX_ATTEMPTS` 仍为 `3`，与 `ai4-te1v` 定的 `5` 冲突。边界已成形，数值修正由 `ai4-10ja` 承接，不在本票处理。

## Next implementation boundary

本票的架构决策已与 `ai4-te1v` 的最终消息协议对齐。后续真实实现应拆分为独立适配票，不在本票中引入具体 Redpanda Python 客户端。

- `ai4-2982` 已收敛并关闭；coordinator 通过 research-map 管理 MCP 的 `get_formal_mapping_at_revision` 读取正式快照，不直连 SQLite 或 TerminusDB。
- `ai4-nfty` 已收敛并关闭；Task Agent 按 `agent_id` 订阅 `sciweave.task-handoff.<agent_id>`，按 `mapping_domain_id + agent_id` 派生 consumer group，并维护 Inbox 等待 binding。
- `ai4-zc85` 已收敛并关闭；协调核心输入、输出、PendingHandoff、HandoffDispatch、重试、死信和三层恢复边界由其承载。
- `ai4-1y6q` 已完成 Fake ports 协调核心实现，不包含真实 Redpanda 适配。
- 首版 `human_notification_intent` 通过 email-service MCP，不消费通知 topic；邮件成功不等于任务完成。
- 真实 Redpanda producer/consumer、handoff coordinator 部署适配和 `deploy-task-agent` subscriber 由后续实现票承接，并必须引用 `ai4-te1v` 的统一消息信封、消息类型、路由键和 offset 语义。

## Decisions so far

- handoff coordinator 是 `dependency-notice` 的主消费者和 `task_handoff_ready` 的唯一生产者；Task Agent、Centre Agent 和 email-service 不直接发布任务交接。
- `PendingHandoff` 与 `HandoffDispatch` 归 handoff coordinator 自己的持久化边界；Task Agent、Centre Agent 和 email-service 只保存各自执行或投递事实。
- `TaskNode.executor_refs` 决定执行资格；Registry 只提供身份和实例登记事实，不授予权限。
- PO 不直接操作 Redpanda、SQLite 或领域存储；根任务通过幂等 `dispatch_root_task` 进入同一任务交接发布路径。

## Notes

**2026-10-26 核心缺陷修复落地（hanjiang，代码修复；验收记录归 ai4-10ja assignee）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

`ai4-10ja`（Frank Qi 负责）审计的 7 项 coordinator 核心缺陷已在本分支完成**代码修复**（提交 `db2b791`），测试按其契约重写。属人规则只约束 ticket 文档；代码修复已附带回归测试与真实 e2e 证据，验收勾选与 Notes 记录仍由 `ai4-10ja` assignee 完成，本票只记录事实供其复核：

1. 去重键不再含触发 revision（同节点同版本同消息类型只派发一次）；
2. `done` 为终结态，重算不回退 `waiting`；store 增加状态迁移守卫（同状态幂等允许）；
3. `executor_refs` 按声明顺序选第一个可用 Agent，拒绝"只取第一个"；
4. 无入边根节点不自动派发，新增 `dispatch_root_task`（幂等、拒绝非根节点）；
5. `max_attempts` 达到上限转 `dead` 不重放，默认值 5；
6. 通知收件人改 `task_owner_id`（人工通知）与 `latest_published_by`（终点汇总，ADR-0004），缺失时保留 waiting 并记录 `recipient_unresolved`；
7. `startup_scan` 与 `_retry_dispatch` 的快照错误处置统一为可重试（保持事实等待）。

验证：coordinator 26 passed + 2 skipped（集成 opt-in）；真实 TerminusDB+Redpanda e2e 在新契约下复跑通过（根节点改为显式 dispatch_root_task）。`FormalSnapshot.latest_published_by` 由适配器从 MCP 响应的 `published_by` 读取（该字段由 `ai4-2raq` 补齐 MCP 返回后生效）。其余缺陷由 `ai4-10ja` 承接验收。

**2026-10-26 真实适配器落地（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

`ai4-2982`（正式快照查询接口）已 closed 且 `get_formal_mapping_at_revision` 已在 research-map 落地；`ai4-1y6q`（协调核心）已 closed。本轮把协调服务从「Fake ports 验证」推进到「真实中央适配器」，提交 `be62fde`、`574bbd0`：

- **正式快照**：`adapter_snapshot.py` 经 research-map 管理 MCP `get_formal_mapping_at_revision`（ai4-2982 契约）读取一致快照，投影为 `FormalSnapshot`；`no_such_revision`/`inconsistent`/`unavailable` 按稳定错误分层映射（`NoSuchRevisionError`/`SnapshotInconsistentError`/`SnapshotUnavailableError`）。
- **派发发布**：`adapter_publisher.py` 用 kafka-python 向固定物理 topic `sciweave.task-handoff.<agent_id>` 发布 `task_handoff_ready`（消息交接恢复契约）；未配置目标 agent 时可选静默（由协调器保留等待事实）。
- **执行者可用性**：`adapter_registry.py` 经 Registry MCP `get_agent_registration` 查询；仅 `active` 且有 `online` 实例视为可用，Registry 事实不构成执行授权（符合决策基线第 6 条）。
- **人工通知**：`adapter_email.py` 经 email-service MCP `send_notification` 提交通知意图；未配置时降级为保留等待事实（符合「邮件成功不等于任务完成」边界）。
- `src/main.py` 汇总启动：环境变量驱动端点/令牌，启动扫描 + 非终态派发轮询重试。新增依赖 `kafka-python>=3.0.11,<4`（uv.lock 已锁）。

验证：coordinator 17 项单元/适配器测试全绿（进程内 MCP stub 覆盖快照投影、稳定错误分层、Registry 可用性判定、通知载荷）；新增真实 TerminusDB 集成测试（`test_terminus_integration.py`，显式 `SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`）本机实测通过——临时库种正式 T1→T2 路线 + DependencyEdge，经真实管理 MCP 由 `ResearchMapMcpSnapshotPort` 读回，节点/executor_refs/owner/边投影全部正确。真实读取暴露并修复了字段形态差异：TerminusDB 把 `source/target_node_version_ref` 存为 JSON 文本而非内联 dict，`_parse_ref` 兼容两种形态。

仍在决策票之外待接线：`formal_revision_published` 事件的 Redpanda 订阅消费（coordinator 的 `on_formal_revision_published` 入站）属于 centre-control 部署层，未并入本子项目。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属并记录，不改写正文与验收标准。

**2026-10-23**：本轮进一步收敛候选和通知边界：取消 `defer`；PO 的候选决策只能是 `formalize`、`request_revision` 或 `reject`。返修必须指定唯一 `repair_owner_id`，由负责人自己的 Task Agent 执行；Centre Agent 只预审，不返修。混合候选不可行时，PO 可以指派负责人组织返修或通过高权限 MCP 创建新混合候选。无后续 TaskNode 时发送 `task_terminal_summary` 通知 PO，PO 通过 MCP 创建后续候选，不直接操作队列。相关 PO 工具边界另见「PO 候选裁决、返修指派与根任务分派 MCP」。

**2026-10-26 消息协议同步（Frank Qi）**

依据 `ai4-te1v` Grill-with-docs 收敛结果，同步本票：首版不消费 Redpanda notification topic；coordinator 只通过 `dependency-notice` 接收 `formal_revision_published` 与 `task_completed`，通过 `sciweave.task-handoff.<agent_id>` 发布 `task_handoff_ready`；治理事件使用共享 `sciweave.governance-events`。真实 Redpanda 适配和部署实现不回填到本架构票，由后续实现票承接。

## Resolution

本票作为交接协调服务的决策分支关闭。13 条验收全部勾选，依据写在各条之后。

关闭的含义是**边界与契约已定**，不是**代码已就位**。当前实际状态：`sci-weave/centre-control/coordinator/` 只有核心状态机，`src/main.py` 只读配置、开 SQLite、打日志、关连接，四个 Port 全是 Protocol，没有任何真实适配器。

承接票：

- [修复 handoff coordinator 派发幂等与执行者选择缺陷](ai4-10ja.md)：七个已复现缺陷，含根任务 `dispatch_root_task` 缺失实现、`DISPATCH_DEAD` 从未写入、收件人取值错误。
- [handoff coordinator 快照适配器接入 research-map 正式快照](ai4-edrp.md)：首个真实适配器，决定收件人规则能否真正生效。
- [实现消息信封纯协议包](ai4-3zxu.md)：`HandoffPublisherPort` 的前置。
- [记录 mcp-libs 标准卡片工具面漂移并延后补齐](ai4-ced7.md)、[确认 Registry MCP 接口冻结并解除 email-service 联调前置](ai4-1kls.md)：另两条适配器链路的未决前置。
