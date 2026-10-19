# SciWeave Gateway MVP

这是 Gateway 的最小 HTTP 与 SQLite 闭环。当前版本只负责接收 Owner Command、保存平台状态并提供执行查询；Worker 调度和 `fast-agent-mcp` Runtime Adapter 由后续工单实现。

## 目录

```text
src/main.py       # 子项目启动入口
src/gateway/      # Gateway 业务模块
tests/            # 自动化测试
pyproject.toml    # Python 项目、依赖和启动命令声明
.env              # 本机环境变量，不提交
.env.example      # 可提交的环境变量示例
```

`gateway` 是简洁的 Python 业务模块名；`sci-weave/gateway` 是项目目录。后续若增加“端侧 Agent Gateway”等子项目，可使用更具体的项目目录名，同时保留符合职责的模块名。

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

## HTTP seam

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

当前不包含 Worker、真实 `fast-agent-mcp` 调用、领域 MCP、消息队列或 A2A。
