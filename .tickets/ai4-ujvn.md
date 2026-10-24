---
id: ai4-ujvn
status: closed
deps: [ai4-we38]
links: [ai4-we38, ai4-yyy9, ai4-u3rs, ai4-9322, ai4-6ljq, ai4-orpg, ai4-w73z, ai4-0s02, ai4-z3z4]
created: 2026-10-21T21:06:00Z
type: feature
priority: 1
assignee: Frank Qi
tags: [agent, task-agent, mcp, registery, ready-for-agent]
---
# Registry 登记事实与中央服务开放面规格

## Problem Statement

端侧 Task Agent 由研究员自持后，平台需要知道谁在运行什么 Workflow Agent、由哪个主体持有、有哪些运行实例以及通知联系人。同时，中央服务需要向受控调用方提供登记和查询能力，但 Registry 不能演变为统一授权源，也不能保存第二份 TaskNode 执行关系。

## Solution

建立最小 Registry 事实登记边界，提供受鉴权的登记/查询 MCP。Registry 保存 Principal、Workflow Agent、Agent Instance 和当前通知联系人事实；登记工具只追加或标记状态变化，查询工具只返回事实。TaskNode 执行资格继续由正式 Map 的 `executor_refs` 决定，服务能力继续由各自 MCP 的调用方能力面决定。

Registry 与 email-service 解耦：email-service 通过 `RecipientResolver` 调用 Registry 的只读联系人查询，再向 email-service 自己的 `send_notification` MCP 提交通知，不直连 Registry 存储，不把联系人查询当作授权依据。

## User Stories

1. 作为研究员，我希望登记自己创建的 Workflow Agent，以便平台知道哪个 Agent 属于我。
2. 作为研究员，我希望登记 Agent 运行实例，以便平台知道同一 Agent 的实例状态。
3. 作为 Project Owner，我希望登记 Principal 和中央 Agent，以便平台保留完整的事实账本。
4. 作为 email-service，我希望按 `principal_id` 查询当前有效联系人，以便发送通知而不复制联系人数据库。
5. 作为中央服务，我希望查询 Agent 登记和实例状态，以便生成配置提示和诊断信息。
6. 作为系统维护者，我希望登记记录不包含权限清单，以便 Registry 不成为统一授权源。
7. 作为 Project Owner，我希望 Agent 注销后仍保留历史记录，以便追溯过去的运行事实。
8. 作为研究员，我希望能够标记 Agent 恢复，使离线 Agent 的登记状态可更新。
9. 作为多实例 Workflow 持有人，我希望同一 `agent_id` 支持多个 `agent_instance_id`，以便多个实例共享任务消费组。
10. 作为 Registry 调用方，我希望重复登记具有幂等结果，以便重试不会产生重复身份事实。
11. 作为审计人员，我希望每个 MCP 登记/查询调用都有访问账本记录，以便追溯谁访问或修改了登记事实。
12. 作为系统维护者，我希望 Registry 不修改正式 Map，以便登记变更不会隐式改变 TaskNode 执行关系。

## Implementation Decisions

- Registry 提供受鉴权的 MCP 工具：`register_principal`、`register_workflow_agent`、`register_agent_instance`、`get_principal_contact`、`get_agent_registration` 和 `health`。
- 登记工具不提供物理删除；支持状态标记和恢复：Principal 使用 `active/disabled`，Workflow Agent 使用 `active/retired`，Agent Instance 使用 `starting/online/offline/revoked`。注销、恢复和运行状态变化都保留历史登记记录并追加状态变化。
- Principal 最小字段为：`principal_id`、`role`（`researcher` 或 `project_owner`）、当前 `contact_email`、登记状态、记录时间和更新时间。
- Workflow Agent 最小字段为：`agent_id`、`workflow_id`、`kind`（`endpoint` 或 `centre`）、所属 `principal_id`（`endpoint` 必填、`centre` 留空）、`workflow_kind`、`created_by`、登记状态、记录时间和更新时间。
- Agent Instance 最小字段为：`agent_id`、`agent_instance_id`、运行状态、`last_seen_at`、记录时间和更新时间。同一 `agent_id` 可登记多个实例；相同实例重复登记采用幂等更新。
- Registry 不保存 `allowed_mcp`、`readable_task_nodes`、`writable_namespaces`、`executor_refs`、TaskNode 集合、模型凭据、SMTP 凭据或部署主机网络地址。
- 研究员注册自己的 Task Agent 后，可以登记和更新自己持有的 `endpoint` Agent 与实例；不能登记 `centre` Agent，不能修改其他主体的登记记录。Project Owner 可以登记 Principal、endpoint Agent 和 centre Agent。Centre 服务按最小读取面查询事实；email-service 只通过 `RecipientResolver` 查询联系人，不获得 Registry 管理写入能力。
- `get_principal_contact` 只返回当前有效联系人及其状态和版本；联系人不存在、缺失、禁用或 Registry 不可用返回稳定错误码：`principal_not_found`、`contact_missing`、`contact_disabled`、`registry_unavailable`。email-service 不把查询结果缓存为授权事实。
- 所有 Registry MCP 调用都经过共享 `audit-trail` 记录访问信息；登记事实与访问账本分开保存。访问账本只记录调用者、通道、服务、工具、目标、结果、错误码和耗时，不记录登记正文、凭据或完整入参。登记写入失败不改变正式 Map，也不修改 `executor_refs`。
- 登记使用 `operation_id`/`idempotency_key` 幂等：同键同内容返回首次结果并标记 `duplicate=true`；同键不同内容返回 `idempotency_conflict`；身份冲突返回 `agent_owner_conflict` 或 `instance_identity_conflict`。
- Registry `health` 提供存储和服务状态，不返回凭据、完整联系人数据或内部异常堆栈。
- Registry MCP 的具体实现、部署和存储适配由后续实现票承载；本票固定事实、工具和开放面契约。
- 目录名沿用现有 `registery` 约定；是否迁移为 `registry` 不属于本票范围。

## Testing Decisions

- 最高测试接缝是认证后的 Registry MCP 调用，验证登记、查询、状态标记、恢复、幂等、权限拒绝和稳定错误码；不测试私有表访问顺序。
- 使用临时 SQLite 验证 Principal、Workflow Agent、Agent Instance 的登记和状态历史；验证注销后记录保留、恢复后追加状态变化和多个实例。
- 使用 Fake audit-trail 验证所有 MCP 调用只记录访问信息，登记事实和访问账本不混用。
- 使用 Fake Registry 查询验证 `get_principal_contact` 的成功、联系人缺失、禁用、版本和服务不可用场景。
- 验证 Registry 登记不会改变正式 Map、`executor_refs`、Task Agent 订阅或 email-service 投递状态。
- 验证研究员、Project Owner、Centre 服务和 email-service 的工具级开放面；验证不同主体不能登记或读取超出范围的事实。
- 使用临时资源、Fake 调用和系统分配端口；不依赖真实凭据、真实邮件、真实消息队列或固定部署端口。

## Out of Scope

- Registry 作为统一权限系统、TaskNode 执行授权源或 MCP 授权清单。
- Registry 修改 Research Mapping、LLM-Wiki、正式 Map、`executor_refs` 或任务分配关系。
- Registry 托管 Task Agent、启动 Worker、管理模型凭据或保存主机网络地址。
- email-service 的邮件发送、SMTP 适配器和投递状态实现。
- Task Agent 动态订阅、consumer group、Inbox 和 Workflow 卡片加载实现。
- Centre Agent 预审规则和 Project Owner 正式化流程。

## Further Notes

- Registry 是“谁在运行什么”的事实账本；执行资格来自正式 Map，调用能力来自各服务端 MCP 的能力面。
- `get_principal_contact` 是 email-service 的联系人事实依赖，但不把两个服务耦合成一个授权或事务边界。
- 本票完成后，Registry 实现票可以独立实现登记/查询 MCP；email-service 先用 Fake `RecipientResolver`，再接入真实 Registry MCP 适配器。

## Notes

**2026-10-23T16:26:37Z**

Resolution（2026-10-24）：本票收敛为 Registry 登记事实与中央服务开放面规格。Registry 通过受鉴权 MCP 提供 Principal、Workflow Agent、Agent Instance 的登记/状态更新和查询；不提供物理删除，注销与恢复通过追加状态变化保留历史。研究员只能登记和更新自己持有的 endpoint Agent/实例，Project Owner 可登记 Principal、endpoint 与 centre Agent，Centre 服务按最小读取面查询；email-service 只通过 RecipientResolver 查询联系人。所有 MCP 访问使用 shared/audit-trail 记录访问信息，Registry 登记事实单独保存。Registry 不保存 executor_refs、TaskNode 关系或授权清单，也不参与 TaskNode 鉴权；执行资格由正式 Map.executor_refs 决定。具体实现由后续 Registry 实现票承载。

**2026-10-23T16:35:18Z**

关闭说明（2026-10-24）：本票此前已完成多轮讨论，现将结论正式视为 Resolution 并关闭。Registry 事实模型、状态标记/恢复、研究员与 Project Owner 开放面、联系人查询、共享访问留痕及非授权边界均已收敛。Centre Agent 第四档能力继续由 ai4-t2wc/ai4-rlv6 承载；具体实现由 ai4-w4su 承载。email-service 先使用 Fake RecipientResolver，真实 Registry 适配在 Registry 实现完成后接入。
