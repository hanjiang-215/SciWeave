# coordinator

独立的交接协调服务。实现正式快照读取端口、`PendingHandoff`/`HandoffDispatch` SQLite 状态、幂等重算和三类输出：`task_handoff_ready`、`human_notification_intent`、`task_terminal_summary`。核心经 Fake ports 验证；真实适配器已接入（research-map 管理 MCP 快照、Redpanda 发布、Registry MCP 可用性、email-service MCP 通知）。

## 职责边界

- 依据正式 Mapping 快照重算依赖条件，维护等待与派发事实（`PendingHandoff`/`HandoffDispatch`）。
- 条件满足且执行者可用时发布 `task_handoff_ready`；执行者不可用时生成 `human_notification_intent` 并保留等待事实。
- 确认节点无后继时向 PO 发送 `task_terminal_summary`。
- 只经查询端口读取正式 Mapping，不直连 Research Mapping SQLite/TerminusDB，不创建 Task Agent 的 ExecutionRecord，不修改正式 Map。

## 真实适配器

- **正式快照**：`adapter_snapshot.py` 经 research-map 管理 MCP `get_formal_mapping_at_revision` 读取一致快照（ai4-2982 契约）；`no_such_revision`/`inconsistent`/`unavailable` 按稳定错误分层映射。
- **派发发布**：`adapter_publisher.py` 用 kafka-python 向 `sciweave.task-handoff.<agent_id>` 发布 `task_handoff_ready`（消息交接恢复契约的固定物理 topic）。
- **执行者可用性**：`adapter_registry.py` 经 Registry MCP `get_agent_registration` 查询，返回 `AgentState`：`active` 且有 `online` 实例为 `available`；注册存在但不可运行为 `unavailable`；Registry 明确回 `agent_not_found` 才是 `unregistered`；查询不到（超时、拒绝、存储故障）为 `unknown`，不据此断言执行者已不存在。Registry 事实不构成执行授权。

## 人工通知的三类原因

执行者不可用时保留 `waiting` 并生成一条 `human_notification_intent`，`notification_kind` 取决定收件人下一步动作的那一种：

| 场景 | `notification_kind` | 收件人 |
| --- | --- | --- |
| `executor_refs` 为空 | `workflow_binding_required` | 该节点 `task_owner_id` |
| `executor_refs` 指向未登记的 `agent_id` | `workflow_load_failed` | 该节点 `task_owner_id` |
| 已注销、无可用实例、或只配置人工处理 | `agent_unavailable` | 该节点 `task_owner_id` |
| 派发成功的节点无后继 | `task_terminal_summary` | `FormalSnapshot.latest_published_by` |

发送前经 `PrincipalDirectoryPort` 校验收件人：`absent` 不发送、保留 `waiting` 并记录 `recipient_unresolved:principal_absent`；`unknown`（目录查不到）fail-open 照发——Registry 不可用时静默丢掉全部通知比偶尔误发更糟。

## 快照不可读

`SnapshotUnavailableError` / `SnapshotInconsistentError` / `NoSuchRevisionError` 在事件入口与启动扫描共用 `_handle_unreadable_snapshot`：保留既有事实、写入 `snapshot_failure`（按 domain + revision 去重，读通后清除），派发状态维持 `result_unknown`。`failed` 只表示「代码能做的都做完了」，不当作「这次没读出来」的垃圾桶。
- **人工通知**：`adapter_email.py` 经 email-service MCP `send_notification` 提交通知意图；未配置时降级为保留等待事实。
- **治理事件消费**：`adapter_events.py` 订阅 `sciweave.governance-events`，把 `formal_revision_published` 路由进 `on_formal_revision_published`；候选事件忽略（归 Centre Agent 预审 Workflow）。`KafkaGovernanceEventConsumer` 持消费者组，offset 在整批处理后提交，重放由 PendingHandoff 幂等键挡住。

## 配置

环境变量（`.env.example` 仅示例，不提交真实 `.env`）：

- `SCIWEAVE_COORDINATOR_SQLITE_PATH`：协调状态库路径（必填）。
- `SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS` / `RETRY_MULTIPLIER` / `RETRY_MAX_SECONDS`：重试退避。
- `SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS`：派发轮询间隔。
- `SCIWEAVE_COORDINATOR_MAX_ATTEMPTS`：派发重试上限（默认 5）。
- `SCIWEAVE_MAPPING_MCP_ENDPOINT` / `SCIWEAVE_MAPPING_MCP_TOKEN`：research-map 管理 MCP（必填）。
- `SCIWEAVE_REGISTRY_MCP_ENDPOINT` / `SCIWEAVE_REGISTRY_MCP_TOKEN`：Registry MCP（必填）。
- `SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP`：Redpanda 引导地址（必填）。
- `SCIWEAVE_EMAIL_MCP_ENDPOINT` / `SCIWEAVE_EMAIL_MCP_TOKEN`：email-service MCP（可选）。

## 验证

```bash
uv sync
uv run --env-file .env.example pytest -q
uv run --env-file .env.example python -m compileall -q src tests
```

核心状态机（`PENDING_*`/`DISPATCH_*` 状态机、重复事件去重、Agent 不可用保留等待、派发结果未知在启动扫描恢复）经 Fake ports 验证；真实适配器经进程内 MCP stub 与真实基础设施两级验证：快照投影、稳定错误分层、Registry 可用性判定、通知载荷、治理事件路由、以及真实 Redpanda + TerminusDB 的 `formal_revision_published → task_handoff_ready` 端到端（`test_handoff_e2e.py`，显式标记启用）。