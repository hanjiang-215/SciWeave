# Centre Agent Gateway MCP

中央 Centre Agent 的常驻 MCP 控制面。当前票只实现候选事件触发的一轮固定占位 Agent 执行；预审规则、报告写入和候选合并由后续规格负责。

## 当前入口

- 上游候选事件由 `gateway/ingest` 接收并交给 Gateway；测试使用假队列直接调用候选事件入口。
- `POST /mcp` 需要 `Authorization: Bearer <token>`。
- MCP 提供 `query_execution`、`cancel_execution`、`list_pending`、`answer_question`、`review_execution` 和 `health`。
- `answer_question` 与 `review_execution` 当前返回 `unimplemented`。
- 不提供 `submit_owner_command`，也不提供 `accept`；任务触发来自候选事件，而不是 Owner MCP 命令。

## 本地验证

```bash
cd sci-weave/centre-control/centre-agents
uv sync
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```

服务路径、令牌、数据库位置和 Worker 运行目录由环境变量配置；仓库只提交 `.env.example`。测试使用临时 SQLite、系统分配端口和固定占位运行时，不连接真实队列或模型。
