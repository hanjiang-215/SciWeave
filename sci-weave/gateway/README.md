# SciWeave Gateway MVP

这是 Gateway 的最小 HTTP 与 SQLite 闭环。当前版本只负责接收 Owner Command、保存平台状态并提供执行查询；Worker 调度和 `fast-agent-mcp` Runtime Adapter 由后续工单实现。

## 运行

在仓库根目录执行：

```bash
SCIWEAVE_GATEWAY_TOKEN=local-development-token \
PYTHONPATH=sci-weave \
python3 -m gateway.main
```

默认监听 `127.0.0.1:8080`，数据库文件默认为当前目录下的 `sci-weave-gateway.sqlite3`。可以通过以下环境变量覆盖：

- `SCIWEAVE_GATEWAY_TOKEN`：本地开发令牌，必须由环境注入，不提交真实值。
- `SCIWEAVE_GATEWAY_DB`：SQLite 文件路径。
- `SCIWEAVE_GATEWAY_HOST`：监听地址。
- `SCIWEAVE_GATEWAY_PORT`：监听端口。

## HTTP seam

健康检查不要求令牌：

```bash
curl http://127.0.0.1:8080/health
```

提交 Owner Command：

```bash
curl -X POST http://127.0.0.1:8080/v1/commands \
  -H 'Authorization: Bearer local-development-token' \
  -H 'Content-Type: application/json' \
  -d '{"task_node_id":"node-1","command":"inspect","idempotency_key":"demo-1"}'
```

查询执行记录：

```bash
curl -H 'Authorization: Bearer local-development-token' \
  http://127.0.0.1:8080/v1/executions/<execution_id>
```

## 测试

本票只使用 Python 标准库，不新增产品运行时依赖。测试使用 `unittest`，从 Gateway 的 HTTP 公共 seam 验证健康检查、令牌校验、SQLite 初始记录、查询和幂等重复提交：

```bash
PYTHONPATH=sci-weave \
python3 -m unittest discover -s sci-weave/gateway/tests -v
```

当前不包含 Worker、真实 `fast-agent-mcp` 调用、领域 MCP、消息队列或 A2A。
