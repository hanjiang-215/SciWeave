# Task Agent Gateway MCP 角色

此子项目提供 SciWeave Task Agent 的常驻 Gateway MCP v1 入口。Task Owner 的 MCP 客户端通过经认证的 Streamable HTTP 调用提交和查询命令；Gateway 将调用者、命令留痕、稳定 Task 会话、初始执行记录与审计事件保存到 SQLite。回环 HTTP 只暴露最小健康探针。

本阶段不包含消息队列消费、Worker 调度、fast-agent Runtime Adapter 或领域 Buffer。

## 配置与运行

```bash
cd sci-weave/task-agent/gateway/mcp
cp .env.example .env
# 编辑 .env
uv run --env-file .env sciweave-task-agent-gateway-mcp
```

环境变量：

- `SCIWEAVE_GATEWAY_TOKEN`：本地开发 Bearer 令牌。
- `SCIWEAVE_GATEWAY_CALLER_ID`：写入命令与审计事实的本地调用者标识。
- `SCIWEAVE_GATEWAY_DB`：SQLite 数据库位置。
- `SCIWEAVE_GATEWAY_HOST`：监听地址。
- `SCIWEAVE_GATEWAY_PORT`：监听端口。

## 接口

- `POST /mcp`：需要 `Authorization: Bearer <token>`。支持 MCP 初始化、`tools/list`，以及 `submit_owner_command`、`query_execution`、`health` 三个工具。
- `GET /health`：仅返回 `status` 与 `gateway_api_version`，不需要令牌。

`submit_owner_command` 的 `idempotency_key` 在该工具内全局唯一。相同键的重试返回第一次保存的命令和执行标识，并标记 `duplicate: true`。

## 回归测试

从项目组根执行：

```bash
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```
