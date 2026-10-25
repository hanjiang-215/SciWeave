# coordinator

独立的交接协调核心。首版实现正式快照读取端口、`PendingHandoff`/`HandoffDispatch` SQLite 状态、幂等重算和三类输出：`task_handoff_ready`、`human_notification_intent`、`task_terminal_summary`。真实 Research Mapping MCP 与 Redpanda 适配器待对应契约票收敛后接入。

## 职责边界

- 依据正式 Mapping 快照重算依赖条件，维护等待与派发事实（`PendingHandoff`/`HandoffDispatch`）。
- 条件满足且执行者可用时发布 `task_handoff_ready`；执行者不可用时生成 `human_notification_intent` 并保留等待事实。
- 确认节点无后继时向 PO 发送 `task_terminal_summary`。
- 只经查询端口读取正式 Mapping，不直连 Research Mapping SQLite/TerminusDB，不创建 Task Agent 的 ExecutionRecord，不修改正式 Map。

## 配置

环境变量（`.env.example` 仅示例，不提交真实 `.env`）：

- `SCIWEAVE_COORDINATOR_SQLITE_PATH`：协调状态库路径（必填）。
- `SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS` / `RETRY_MULTIPLIER` / `RETRY_MAX_SECONDS`：重试退避。
- `SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS`：派发轮询间隔。
- `SCIWEAVE_COORDINATOR_MAX_ATTEMPTS`：派发重试上限（默认 3）。

## 验证

```bash
uv sync --dev
uv run --env-file .env.example pytest -q
uv run --env-file .env.example python -m compileall -q src tests
```

当前核心通过 Fake ports 验证（`PENDING_*`/`DISPATCH_*` 状态机、重复事件去重、Agent 不可用保留等待、派发结果未知在启动扫描恢复）。真实适配器（research-map MCP 快照、Redpanda 发布、email-service 通知、Registry 可用性）接入后 `src/main.py` 汇总启动入口。