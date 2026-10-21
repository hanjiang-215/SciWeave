# SciWeave Task Agent

`task-agent` 是 SciWeave 的 Task Agent 项目组。它以独立 Python 子项目划分三个进程角色：

- `gateway/mcp`：常驻 Gateway MCP 接入与当前 HTTP 回环调试 seam；接收 Owner 命令并保存执行状态。
- `gateway/ingest`：常驻上游交接消费角色；当前仅提供可安装骨架，不实现消息队列消费。
- `worker`：由 Gateway 启动的短生命周期 fast-agent-mcp Worker loop；当前仅提供可安装骨架，不实现运行时 loop。

`gateway/mcp` 与 `gateway/ingest` 不共享 Python 代码。未来可共享同一 SQLite 文件，但表归属、双入口租约与恢复语义由对应 Gateway 规格票决定，当前未实现。

## Gateway 联合启动

Gateway 与 Worker 仍各自维护 `.env`。本地联调时由启动 shell 显式注入两份配置，源码不会读取 `.env`：

```bash
cd sci-weave/task-agent
set -a
. worker/.env
. gateway/mcp/.env
set +a
uv run --package sciweave-task-agent-gateway-mcp sciweave-task-agent-gateway-mcp
```

真实 DeepSeek Key 只保留在 `worker/.env`，不会提交；未配置 Key 时 Gateway 可使用不调用模型的 passthrough 运行时。

## 工作区

项目组根使用 uv workspace 并维护唯一 `uv.lock`：

```bash
cd sci-weave/task-agent
uv sync
```

运行 Gateway MVP 回归测试：

```bash
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```

各角色只从其本地 `.env` 读取配置；仓库只提交 `.env.example`。Docker/Compose 组合部署将在常驻角色具备实际启动行为后再添加。
