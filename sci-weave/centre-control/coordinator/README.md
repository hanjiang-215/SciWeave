# coordinator

独立的交接协调核心。首版实现正式快照读取端口、`PendingHandoff`/`HandoffDispatch` SQLite 状态、幂等重算和三类输出：`task_handoff_ready`、`human_notification_intent`、`task_terminal_summary`。真实 Research Mapping MCP 与 Redpanda 适配器待对应契约票收敛后接入。

## 验证

```bash
uv sync
uv run --env-file .env pytest -q
uv run --env-file .env python -m compileall -q src tests
```

服务地址、数据库路径和凭据通过 `.env` 配置；仓库只提交 `.env.example`。
