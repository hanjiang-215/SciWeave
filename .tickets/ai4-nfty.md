---
id: ai4-nfty
status: closed
deps: []
links: []
created: 2026-10-23T11:59:41Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-te1v
tags: [wayfinder:grilling, message-queue, task-agent, agent, handoff]
---
# 研究员 Task Agent 动态订阅 task-workflow 交接消息

明确研究员创建新的 task-workflow 后，端侧 Task Agent 如何发现并订阅目标 TaskNode 的 task_handoff_ready。正式 Map.executor_refs 是执行关系权威，Registry 不保存第二份任务分配事实。

## Design

### 发现与订阅衔接

- 长期本地 binding 按 `agent_id → workflow_id` 保存；`workflow_id` 用于定位本地 Workflow 卡片，加载 Workflow 定义和启动进程。每条 Inbox/ExecutionRecord 仍保存精确的 `target_node_version_ref`。
- 新 Workflow 创建后：Workflow 卡片创建 → `workflow_id`/`agent_id` 登记到 Registry → 正式 `executor_refs` 发布 → 端侧 subscriber 发现 `agent_id` 归属并订阅目标 topic。
- 启动/运行时通过正式 Map 查询或事件补偿发现新分配，不依赖 Registry 登记充当执行授权。

### Topic 与消费者组

- 物理 topic 模板 `sciweave.task-handoff.<agent_id>`，不按 TaskNode 创建 topic；一个 Agent 可负责多个 TaskNode，同一 Agent 的多个实例共享同一个 consumer group 竞争消费。
- consumer group 由 `mapping_domain_id` 与 `agent_id` 派生：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`。重新上线继续消费未提交 offset。
- `task_handoff_ready` 必须携带 `target_agent_id` 和 `target_node_version_ref`；subscriber 校验二者与本地 Agent 身份和正式执行关系，topic 隔离不能替代 `executor_refs` 鉴权。
- Agent 注册完成且具备接收任务条件时创建 topic；注销不删除 topic 或注册记录，只标记注销/不可用。离线时 topic 和未消费消息保留。

### Inbox 与错误处置

- 消息先到但本地没有 Workflow binding 时，写入 `InboxMessage(status=awaiting_workflow_binding)`，不创建 Worker、不标记执行失败、不丢弃消息；binding 建立后扫描 Inbox，加载 Workflow 卡片并转为 `queued ExecutionRecord`。
- Workflow 卡片缺失、版本不兼容、加载或启动失败时，Inbox 保留原消息并进入可观察配置错误状态，生成 `human_notification_intent`；不回写或修改正式 Map。
- 执行者转移后，旧 Agent 已进入 Inbox 的消息不自动删除；未创建执行记录的旧消息按最新正式 Map 校验，目标已变更则标记 `superseded`，等待新正式版本生成新交接消息；新消息只发到新 `target_agent_id` 的 topic。
- 服务启动使用原 consumer group 恢复 offset，并扫描 Inbox 中的 `awaiting_workflow_binding`、可重试和待派发记录；消息过期后依赖正式 Mapping 和未完成本地事实补偿发现。

### Registry 边界

Registry 只提供 `agent_id`、`agent_instance_id` 和运行登记事实；正式 Map.executor_refs 决定 TaskNode 执行资格。本地 binding 不是授权，registry 登记不授予执行资格。

## 需要裁决的问题（已收敛，见 Current decision baseline）

以下问题已逐条裁决并落入 baseline：发现与订阅衔接、topic 隔离与 consumer group、历史消息与离线恢复、补偿发现、幂等与安全边界、Registry 非授权源、Workflow binding 定位。

## Current decision baseline

- 长期本地 binding 按 `agent_id → workflow_id` 保存；`workflow_id` 用于定位本地 Workflow 卡片，加载 Workflow 定义和启动进程。每条 Inbox/ExecutionRecord 仍保存精确的 `target_node_version_ref`。
- 采用按逻辑 Agent 隔离的物理 topic 模板：`sciweave.task-handoff.<agent_id>`。不按 TaskNode 创建 topic；一个 Agent 可负责多个 TaskNode；同一 Agent 的多个实例共享同一个 consumer group 并竞争消费。
- Agent 注册完成且具备接收任务条件时创建对应 topic；Agent 注销不删除 topic 或注册记录，只标记注销/不可用状态。Agent 离线时 topic 和未消费消息保留，消息处理失败不修改正式 Map，只产生可观察的配置错误或本地 Inbox 状态。
- Task Agent consumer group 由 `mapping_domain_id` 与 `agent_id` 派生：`sciweave.task-workflow.<mapping_domain_id>.<agent_id>`。同一 Agent 的多个实例复用该组，重新上线继续消费未提交 offset。
- `task_handoff_ready` 必须携带 `target_agent_id` 和 `target_node_version_ref`。subscriber 仍校验二者与本地 Agent 身份和正式执行关系，topic 隔离不能替代正式 Map.executor_refs 鉴权。
- 消息到达但本地没有 Workflow binding 时，先写入本地 `InboxMessage(status=awaiting_workflow_binding)`，不创建 Worker、不标记执行失败、不丢弃消息；binding 建立后扫描 Inbox，加载 Workflow 卡片并转为 `queued ExecutionRecord`。
- Workflow 卡片不存在、版本不兼容、加载失败或进程启动失败时，Inbox 保留原消息并进入对应的可观察配置错误状态，生成 `human_notification_intent`；这些错误不回写或修改正式 Map。
- Agent 执行者转移后，旧 Agent 已进入 Inbox 的消息不自动删除；未创建执行记录的旧消息按最新正式 Map 校验，目标已变更则标记 `superseded`，等待新正式版本生成新的交接消息。新消息只发送到新 `target_agent_id` 的 topic。
- Registry 只提供 agent_id、agent_instance_id 和运行登记事实；正式 Map.executor_refs 决定 TaskNode 执行资格。
- 服务启动使用原 consumer group 恢复未提交 offset，并扫描 Inbox 中的 `awaiting_workflow_binding`、可重试和待派发记录；消息过期后依赖正式 Mapping 和未完成本地事实补偿发现。

## Acceptance Criteria

- [x] 明确新 task-workflow 从 Workflow 卡片创建、workflow_id/agent_id 登记、executor_refs 正式发布到端侧订阅生效的流程
- [x] 明确 workflow_id 如何定位 Workflow 卡片、加载 Workflow 定义并启动进程
- [x] 明确 task-handoff 按 agent_id 隔离 topic 的命名、创建/订阅生命周期和 target_agent_id 校验
- [x] 明确 Agent 注册创建 topic、注销只标记不删除、离线保留 topic/消息和配置失败可观察且不改变正式 Map
- [x] 明确 consumer group、offset、历史消息、订阅变更、离线重连和补偿扫描
- [x] 明确 consumer group 由 mapping_domain_id + agent_id 派生，同一 Agent 多实例共享消费组
- [x] 明确多个 Agent 实例竞争消费和执行者转移语义，旧消息不可越权执行
- [x] 明确消息先到时 Inbox 等待 binding，binding 建立后自动派发
- [x] 明确 Workflow 卡片缺失、版本不兼容、加载/启动失败的 Inbox 错误状态和通知边界
- [x] 明确 Registry 只提供身份事实，正式 Map 决定执行资格
- [x] 形成可供 Task Agent subscriber 实现票引用的验证场景

## Notes

**2026-10-25 规格收口（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

Design 从「需要决定的问题」收口为现行语义：发现衔接（卡片创建→登记→executor_refs 发布→订阅）、topic/consumer group 命名、Inbox 等待 binding 与配置错误处置、执行者转移、启动恢复与补偿。决策基线沿用 2026-10-23 轮次与 ai4-z3z4 的订阅器语义，`task_handoff_ready` 载荷与 ai4-zc85 输出契约一致（`target_agent_id` + `target_node_version_ref`）。验收十一项全部勾选，置 closed；实现类验收（真实 Redpanda 订阅、动态 topic 生命周期）依赖 ai4-te1v 消息语义收敛后接入。

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23**：本轮确认：Workflow 注册完成且具备接收任务条件时创建 `sciweave.task-handoff.<agent_id>`；注销不删除 topic 或注册记录，只标记注销/不可用；离线保留 topic 和消息。consumer group 由 `mapping_domain_id + agent_id` 派生，同一 Agent 多实例共享。Workflow 卡片缺失、版本不兼容、加载或启动失败时保留 Inbox 消息，生成可观察配置错误和人工通知，不修改正式 Map。
