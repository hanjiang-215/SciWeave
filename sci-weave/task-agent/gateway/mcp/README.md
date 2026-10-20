# Task Agent Gateway MCP 角色

此子项目承载现有 Gateway MVP：本地 HTTP 回环调试 seam、SQLite 命令持久化及执行查询。Owner 的正式入口将由后续实现替换为 MCP（Streamable HTTP）；现有 HTTP 路径只保留作健康检查、本地调试和测试。

## 配置与运行

```bash
cd sci-weave/task-agent/gateway/mcp
cp .env.example .env
# 编辑 .env
uv run --env-file .env sciweave-task-agent-gateway-mcp
```

环境变量：

- `SCIWEAVE_GATEWAY_TOKEN`：本地开发令牌。
- `SCIWEAVE_GATEWAY_DB`：SQLite 数据库位置。
- `SCIWEAVE_GATEWAY_HOST`：监听地址。
- `SCIWEAVE_GATEWAY_PORT`：监听端口。

## 回归测试

从项目组根执行：

```bash
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```

当前不包含消息队列消费、Worker 调度、fast-agent-mcp Runtime Adapter 或 MCP 工具层。
