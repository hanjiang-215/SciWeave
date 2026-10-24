# Registry

Registry 记录 Principal、Workflow Agent、Agent Instance 和当前通知联系人。它提供带认证的 MCP Streamable HTTP（`/mcp`）以及独立的 HTTP 健康探针（`/health`）。Registry 不决定 TaskNode 能否执行，正式 Mapping 的 `executor_refs` 仍然是执行资格的依据。

调用身份由 `SCIWEAVE_REGISTRY_TOKENS_JSON` 把 bearer token 映射到 `caller_id`、`caller_type`，以及研究员的 `principal_id` 或服务的 `service_role`（`centre` / `email`）。不要在请求头里自报身份。审计库路径使用 `SCIWEAVE_AUDIT_SQLITE_PATH`，由 Registry 传给共享 audit-trail，不在账本包里读环境变量。

## 验证

```bash
uv sync --dev
uv run --env-file .env.example pytest -q
uv run --env-file .env.example python -m compileall -q src tests
```
