# SciWeave Gateway MVP

这是 Gateway 的最小闭环。当前版本只负责接收 Owner Command、保存平台状态并提供执行查询；Worker 调度和 `fast-agent-mcp` Runtime Adapter 由后续工单实现。

## 入口演进

当前已实现的是 HTTP 公共 seam（`/health`、`POST /v1/commands`、`GET /v1/executions/{id}`）。按 `.tickets/ai4-353s.md` 的 2026-10-19 决策修订，**Owner 主通道将改为 MCP（Streamable HTTP）**：Task Owner 的 harness（Codex、Cursor 等）在 `mcp_servers` 中注册 Gateway 地址与令牌，Gateway 作为 MCP server 暴露 `submit_owner_command`、`query_execution`、`cancel_execution`、`list_pending`、`health` 五个工具。

已有 HTTP 端点保留为回环健康检查、本地调试和测试 seam；底层 SQLite 事务、幂等与审计逻辑不需要重写。MCP 工具层由后续实现票覆盖。

## 目录

```text
src/main.py       # 子项目启动入口
src/gateway/      # Gateway 业务模块
tests/            # 自动化测试
pyproject.toml    # Python 项目、依赖和启动命令声明
.env              # 本机环境变量，不提交
.env.example      # 可提交的环境变量示例
```

`gateway` 是简洁的 Python 业务模块名；`sci-weave/gateway` 是项目目录。该目录后续将并入多进程角色的 task-agent 项目组，届时业务模块名保持不变。

## 配置与运行

创建本机配置，不提交真实令牌：

```bash
cd sci-weave/gateway
cp .env.example .env
# 编辑 .env
```

使用 `uv` 创建环境、安装项目并由 `pyproject.toml` 声明的脚本启动：

```bash
uv sync
uv run --env-file .env sciweave-gateway
```

`.env` 中的所有变量均为必填项：

- `SCIWEAVE_GATEWAY_TOKEN`：本地开发令牌。
- `SCIWEAVE_GATEWAY_DB`：SQLite 数据库路径。
- `SCIWEAVE_GATEWAY_HOST`：监听地址。
- `SCIWEAVE_GATEWAY_PORT`：监听端口。

## HTTP seam（回环调试与测试）

从 `.env` 读取地址、端口和令牌后，可以执行：

```bash
set -a
source .env
set +a
curl "http://${SCIWEAVE_GATEWAY_HOST}:${SCIWEAVE_GATEWAY_PORT}/health"
```

提交 Owner Command：

```bash
curl -X POST "http://${SCIWEAVE_GATEWAY_HOST}:${SCIWEAVE_GATEWAY_PORT}/v1/commands" \
  -H "Authorization: Bearer ${SCIWEAVE_GATEWAY_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"task_node_id":"node-1","command":"inspect","idempotency_key":"demo-1"}'
```

## 测试

测试使用 Python 标准库 `unittest`，从 Gateway 的 HTTP 公共 seam 验证健康检查、令牌校验、SQLite 初始记录、查询和幂等重复提交：

```bash
cd sci-weave/gateway
uv run python -m unittest discover -s tests -v
```

当前不包含 Worker、真实 `fast-agent-mcp` 调用、领域 MCP 或消息队列；MCP 工具层尚未实现。
