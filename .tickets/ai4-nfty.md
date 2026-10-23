---
id: ai4-nfty
status: open
deps: []
links: []
created: 2026-10-23T11:59:41Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-te1v
tags: [wayfinder:grilling, message-queue, task-agent, agent, handoff]
---
# 研究员 Task Agent 动态订阅 task-workflow 交接消息

明确研究员创建新的 task-workflow 后，端侧 Task Agent 如何发现并订阅目标 TaskNode 的 task_handoff_ready。正式 Map.executor_refs 是执行关系权威，Registry 不保存第二份任务分配事实。

## Design

需要决定：

1. 新 Workflow/Agent 登记、executor_refs 正式发布与端侧订阅发现的衔接；
2. subscriber 使用按 `agent_id` 隔离的 task-handoff topic 时如何按 `target_agent_id`/`target_node_version_ref` 路由和过滤；
3. consumer group 命名、历史消息、订阅变更和离线恢复；
4. 启动/运行时如何通过正式 Map 查询或事件补偿发现新分配；
5. 多个 TaskNode、多个 Agent 实例和执行者转移时的幂等与安全边界；
6. 不能把 Registry 登记本身当成执行授权；
7. 本地 Workflow binding 如何通过 `workflow_id` 定位 Workflow 卡片，加载定义并启动对应进程。

## Current decision baseline

- 长期本地 binding 按 `agent_id → workflow_id` 保存；`workflow_id` 用于定位本地 Workflow 卡片，加载 Workflow 定义和启动进程。每条 Inbox/ExecutionRecord 仍保存精确的 `target_node_version_ref`。
- 采用按逻辑 Agent 隔离的物理 topic 模板：`sciweave.task-handoff.<agent_id>`。不按 TaskNode 创建 topic；一个 Agent 可负责多个 TaskNode；同一 Agent 的多个实例共享同一个 consumer group 并竞争消费。
- `task_handoff_ready` 必须携带 `target_agent_id` 和 `target_node_version_ref`。subscriber 仍校验二者与本地 Agent 身份和正式执行关系，topic 隔离不能替代正式 Map.executor_refs 鉴权。
- 消息到达但本地没有 Workflow binding 时，先写入本地 `InboxMessage(status=awaiting_workflow_binding)`，不创建 Worker、不标记执行失败、不丢弃消息；binding 建立后扫描 Inbox，加载 Workflow 卡片并转为 `queued ExecutionRecord`。
- Agent 执行者转移后，旧 Agent 已进入 Inbox 的消息不自动删除；未创建执行记录的旧消息按最新正式 Map 校验，目标已变更则标记 `superseded`，等待新正式版本生成新的交接消息。新消息只发送到新 `target_agent_id` 的 topic。
- Registry 只提供 agent_id、agent_instance_id 和运行登记事实；正式 Map.executor_refs 决定 TaskNode 执行资格。
- 服务启动使用原 consumer group 恢复未提交 offset，并扫描 Inbox 中的 `awaiting_workflow_binding`、可重试和待派发记录；消息过期后依赖正式 Mapping 和未完成本地事实补偿发现。

## Acceptance Criteria

- 明确新 task-workflow 从 Workflow 卡片创建、workflow_id/agent_id 登记、executor_refs 正式发布到端侧订阅生效的流程
- 明确 workflow_id 如何定位 Workflow 卡片、加载 Workflow 定义并启动进程
- 明确 task-handoff 按 agent_id 隔离 topic 的命名、创建/订阅生命周期和 target_agent_id 校验
- 明确 consumer group、offset、历史消息、订阅变更、离线重连和补偿扫描
- 明确多个 Agent 实例竞争消费和执行者转移语义，旧消息不可越权执行
- 明确消息先到时 Inbox 等待 binding，binding 建立后自动派发
- 明确 Registry 只提供身份事实，正式 Map 决定执行资格
- 形成可供 Task Agent subscriber 实现票引用的验证场景

## Notes

**2026-10-23**：本轮确认：本地 binding 采用 `agent_id → workflow_id`，通过 `workflow_id` 定位 Workflow 卡片并加载定义、启动进程；任务交接物理 topic 按 `agent_id` 隔离，不按 TaskNode 创建；消息先到时写入 Inbox 等待 binding；执行者转移时旧消息未执行则标记 `superseded`，由新正式版本重新生成交接。具体 topic 生命周期、消费者组派生和补偿扫描仍需在本票继续收敛。
