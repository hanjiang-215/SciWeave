---
id: ai4-we38
status: closed
deps: []
links: [ai4-yyy9, ai4-s12u, ai4-z3z4, ai4-iyyn, ai4-csyj, ai4-c2t7, ai4-ufqu, ai4-ujvn, ai4-xem8, ai4-kpvp, ai4-dhpv]
created: 2026-10-21T21:05:00Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [agent, task-agent, endpoint, ready-for-agent]
---
# 研究员端侧 Task Agent 运行与治理边界规格

## Problem Statement

Task Agent 需要执行研究员负责的 TaskNode，但研究员的 Workflow 定义、模型凭据和运行环境属于研究员自己的电脑。中央部署 Task Agent 会迫使平台托管研究员代码和凭据，增加部署、审核、绑定和调试成本，也会模糊 Project Owner、Centre Agent 与 Task Agent 的责任边界。

同时，端侧 Agent 需要接收中央正式路线下发的任务、把结果提交回平台，并接受研究员的人工作业；这些路径必须清楚分离，避免把本地 Operator 控制、正式 Map 授权、Registry 登记和消息投递混成一套权限系统。

## Solution

Task Agent 由研究员在自己的电脑上编写、安装、启动和维护。平台不安装、部署、重启或托管研究员的 Task Agent，也不持有其模型凭据。

Task Agent 通过出站连接订阅中央消息队列中的任务交接。只有正式 Map 的 `TaskNode.executor_refs` 指向该稳定 `agent_id` 时，交接协调服务才会向该 Agent 的任务交接频道发布 `task_handoff_ready`。端侧 Gateway 持久化消息、根据本地 `agent_id → workflow_id` binding 定位 Workflow 卡片并启动执行。

研究员自己的 Codex 通过本机 Gateway MCP 进行查询、回答问题、取消、返修、放弃和人工接管。Gateway MCP 不承担任务下发，任务下发只走消息队列。

Worker 结果写入中央草稿箱。后续一审、候选提交、Centre Workflow 预审和 Project Owner 正式化属于领域治理；只有正式版本发布后，系统才计算并发送下游交接。

Registry 只记录 Principal、Workflow Agent 和 Agent Instance 的身份、持有人、联系人与运行登记事实，不授予 TaskNode 执行权限。Registry 可以通过受鉴权 MCP 提供登记和查询；email-service 通过独立 `RecipientResolver` 查询联系人后发送通知，不直连 Registry 存储，也不把联系人查询当作授权依据。

## User Stories

1. 作为研究员，我希望在自己的电脑上编写和修改 Task Agent，以便快速调试自己的科研 Workflow。
2. 作为研究员，我希望自己启动、停止、重启和维护 Task Agent，以便平台不成为本地运行环境的操作瓶颈。
3. 作为研究员，我希望 Task Agent 使用我自己的模型和工具凭据，以便凭据不需要上传中央服务器。
4. 作为平台维护者，我希望中央不安装、不部署、不重启、不托管研究员 Task Agent，以便中央服务不执行未经平台托管的研究员代码。
5. 作为 Task Agent，我希望通过出站连接订阅任务交接，以便研究员电脑不需要公网入站地址。
6. 作为 Task Agent，我希望只接收正式 Map 分配给我的 `agent_id` 的任务，以便 Registry 登记不会被误当成执行授权。
7. 作为 Task Agent，我希望使用稳定的 `agent_id` 表示逻辑 Workflow Agent，以便同一个 Agent 可以负责多个 TaskNode。
8. 作为 Task Agent，我希望使用 `agent_instance_id` 表示本次部署或运行实例，以便多个实例可以共享消息消费组并竞争消费。
9. 作为 Gateway，我希望通过本地 `agent_id → workflow_id` binding 定位 Workflow 卡片，以便消息到达后能够加载正确的 Workflow 定义。
10. 作为 Gateway，我希望将消息中的目标节点版本保存到 Inbox 和 ExecutionRecord，以便每次执行都能追溯到精确的正式版本。
11. 作为 Gateway，我希望消息先到但本地 Workflow 尚未绑定时保存 Inbox 记录，以便消息不会静默丢失。
12. 作为 Gateway，我希望 Workflow 卡片不存在、版本不兼容、加载失败或进程启动失败时保留原消息并产生可观察错误，以便研究员能够修复配置后重试。
13. 作为 Gateway，我希望同一 Agent 的多个实例使用同一 consumer group，以便同一条交接不会启动多轮并发执行。
14. 作为 Gateway，我希望使用稳定业务键处理至少一次投递，以便重复消息不会重复创建执行。
15. 作为研究员，我希望通过自己的 Codex 调用本机 Gateway MCP，以便查询执行、回答问题、取消、返修或人工接管。
16. 作为研究员，我希望 Gateway MCP 的本地 Bearer token 只认证本机 Operator，以便它不被误解为 TaskNode 授权。
17. 作为 Task Agent，我希望执行结果写入中央草稿箱，以便负责人可以在领域治理流程中审阅结果。
18. 作为 TaskNode Owner，我希望收到草稿完成、执行失败、返修完成和待回答问题的通知，以便及时处理本地执行结果。
19. 作为 TaskNode Owner，我希望把草稿提交为候选，以便结果进入正式领域治理流程。
20. 作为 Centre Workflow，我希望接收候选和正式版本治理事件，以便执行预审，但不负责端侧 Task Agent 返修。
21. 作为 Project Owner，我希望正式化候选后沿正式 DependencyEdge 推进下游，以便下游交接不依赖中央观察到端侧执行状态机。
22. 作为平台维护者，我希望只有正式版本发布才触发下游交接，以便未审核草稿和候选不会绕过治理门禁。
23. 作为 Registry，我希望记录 Principal、Workflow Agent 和 Agent Instance 的事实，以便平台知道谁在运行什么 Agent。
24. 作为 Registry，我希望记录当前有效通知联系人，以便受控服务能够查询收件地址。
25. 作为 Registry，我希望不保存 `executor_refs`、TaskNode 集合或 MCP 授权清单，以便不产生第二份任务分配事实或统一权限源。
26. 作为 Registry 调用方，我希望通过受鉴权 MCP 登记和查询事实，以便登记过程可审计且不依赖直连数据库。
27. 作为 email-service，我希望通过 `RecipientResolver` 查询联系人后发送通知，以便联系人解析与邮件投递保持解耦。
28. 作为平台维护者，我希望 Task Agent、Centre Agent 和 Registry 的能力边界分别表达，以便一个 Agent 的登记不会自动扩展另一个领域的权限。
29. 作为运维人员，我希望看到 Task Agent 的消息连接、Inbox、Workflow 加载和执行状态，以便诊断端侧配置和队列恢复问题。
30. 作为测试维护者，我希望通过消息消费、Gateway MCP 和草稿提交等高层接缝验证行为，以便测试不依赖私有 Worker 实现细节。

## Implementation Decisions

- Task Agent 的运行时归研究员所有；平台不安装、部署、重启、托管其代码或模型凭据。
- Task Agent 通过出站消息连接订阅任务交接；端侧不提供公网入站服务。
- `agent_id` 是注册后稳定的 Workflow Agent 逻辑身份；`agent_instance_id` 表示设备或部署实例；`workflow_id` 用于定位本地 Workflow 卡片。
- Registry 只记录身份、持有人、Workflow 类型、部署描述、实例状态和通知联系人事实，不参与 TaskNode 鉴权，不保存 `executor_refs` 或 TaskNode 关系。
- Registry 提供受鉴权 MCP 登记/查询工具，至少覆盖 Principal、Workflow Agent、Agent Instance、联系人查询、Agent 查询和健康检查；工具面按调用方能力限制，登记不写授权字段。
- 正式 Map 的 `TaskNode.executor_refs` 是任务执行关系权威。只有它指向该 `agent_id` 时，系统才允许生成面向该 Agent 的 `task_handoff_ready`。
- 端侧 Task Agent 的开放面由中央服务端能力面决定：可写入自己的草稿并读取自己的草稿；不得读取他人草稿、写正式存储、审核或正式化候选、修改 `executor_refs`、直接发布任务交接或操作 Redpanda 管理面。
- Gateway MCP 由研究员自己的 Codex 调用，只承担本地执行的查询、回答问题、取消、返修、放弃和人工接管；它不承担任务下发。
- Gateway MCP 的本地 Bearer token 只认证本机 Operator，不表示 TaskNode 授权，也不替代正式 Map 的 `executor_refs`。
- Task Agent 接收消息后先持久化 Inbox；本地 binding 存在时加载 Workflow 卡片并创建 `queued ExecutionRecord`，不存在时保持 `awaiting_workflow_binding`。
- Workflow 卡片不存在、版本不兼容、加载失败或进程启动失败时，消息保留在 Inbox，记录可观察配置错误并通过 email-service MCP 发送通知；不修改正式 Map，不静默丢弃消息。
- Task Agent 与 Centre Agent 都是消息驱动；Task Agent 消费任务交接，Centre Agent 消费候选/正式版本治理事件，二者不互相消费对方的业务消息。
- Worker 结果写入中央草稿箱并保存 `draft_id`；草稿之后的一审、候选、预审和正式化由领域治理流程完成。
- 下游交接触发点是领域正式版本发布，而不是端侧 Worker 完成或本地 Gateway 状态。正式版本发布后沿正式 DependencyEdge 重新计算下游。
- Registry 联系人查询与 email-service 通过 `RecipientResolver` 端口解耦；email-service 只查询联系人事实后提交邮件 MCP，不获得 Registry 管理写入能力。
- 具体 Registry 字段契约、Task Agent subscriber、Workflow 卡片版本和邮件服务实现由各自后续规格/实现票承载；本票只固定它们之间的职责边界。

## Testing Decisions

- 最高测试接缝是端侧消息 subscriber、Gateway MCP 和草稿提交的可观察行为；不测试私有 Worker 类、进程启动命令细节或数据库访问顺序。
- 使用假队列、临时 SQLite、Fake Workflow 卡片加载器、Fake Worker Runtime 和 Fake 草稿箱验证端侧主动订阅、消息幂等、Inbox 等待 binding、加载失败、启动失败和恢复。
- 验证同一 `agent_id` 多实例共享 consumer group、执行者转移后旧消息不得越权启动、新正式版本生成新交接。
- 验证 Gateway MCP token 认证本机 Operator，但不能代替正式 Map 的执行资格。
- 验证 Task Agent 只能写/读自己的草稿，不能调用正式化或任务下发工具。
- 验证 Worker 结果生成草稿，且只有正式版本发布事件才能产生下游交接。
- 验证 Registry 登记/查询 MCP 的事实边界，不写入授权字段；验证联系人查询可被 email-service 的 Fake `RecipientResolver` 使用。
- 使用临时目录、回环地址和系统分配端口；不依赖真实模型、真实队列、真实邮件凭据或固定部署端口。

## Out of Scope

- Registry 的完整独立服务实现、生产部署和真实存储选型；由 Registry 相关规格和实现票承载。
- Task Agent subscriber 的完整实现、topic 生命周期和 consumer group 具体实现；由动态订阅票承载。
- email-service 的 MCP、投递状态和真实发送适配器实现；由邮件服务规格和实现票承载。
- Research Mapping 或 LLM-Wiki 的领域 MCP、候选治理和正式化实现。
- Centre Workflow 的预审规则、报告格式和混合候选实现。
- Redpanda 客户端、MCP SDK、真实模型提供商和生产级部署编排。
- 通过邮件回复驱动候选批准、正式化、任务分派或其他业务状态变更。

## Further Notes

- 本 spec 取代早期“中央部署 Task Agent”的设计；中央不持有研究员 Task Agent 运行时。
- Registry 的登记记录是事实留痕，不是统一授权源；任务执行关系始终以正式 Map `executor_refs` 为准。
- 端侧 Gateway MCP 的职责与业务消息下发严格分离：研究员 Codex 通过 MCP 处置本地执行，Agent 通过消息队列接收正式任务。
- 具体注册表、动态订阅和 Work Agent 实现票应引用本 spec，不重复定义端侧运行归属和权限边界。

## Notes

**2026-10-23T16:14:06Z**

Resolution（2026-10-24）：本票收敛为「研究员端侧 Task Agent 运行与治理边界规格」。Task Agent 由研究员在本机自持，平台不安装、部署、重启或托管其代码和模型凭据；Agent 通过出站消息队列订阅正式任务交接。agent_id 是注册后稳定的 Workflow Agent 逻辑身份，agent_instance_id 表示运行实例，workflow_id 用于定位本地 Workflow 卡片。研究员自己的 Codex 通过本机 Gateway MCP 查询执行、回答问题、取消、返修、放弃和人工接管；Gateway MCP 不承担任务下发，任务下发继续走消息队列。Worker 结果写入中央草稿箱，只有领域正式版本发布后才触发下游交接。

Registry 只记录身份、持有人、Workflow/实例和通知联系人等事实，不是统一授权源，不保存 executor_refs、TaskNode 关系或 MCP 授权清单。Registry 提供受鉴权的登记/查询 MCP：register_principal、register_workflow_agent、register_agent_instance、get_principal_contact、get_agent_registration、health。email-service 通过 RecipientResolver 查询联系人后调用邮件 MCP，不直连 Registry 存储，也不把联系人查询当作授权依据。具体 Registry 字段和实现由 ai4-ujvn 承载；动态订阅由 ai4-nfty 承载。
