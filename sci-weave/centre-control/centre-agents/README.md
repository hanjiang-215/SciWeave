# SciWeave Centre Agent

本目录是中央服务器上的 Centre Agent 项目组，当前以现有 Work Agent 实现作为迁移起点。它包含三个独立 Python 子项目：

- `gateway/mcp`：常驻 Gateway MCP 接入与当前 HTTP 回环调试 seam。
- `gateway/ingest`：常驻上游交接消费角色；当前保留原有可安装骨架。
- `worker`：由 Gateway 启动的短生命周期 Worker；当前保留原有可安装骨架。

本次迁移只调整源码位置，不改变状态机、工具面或 Worker 行为。现行 Work Agent 架构要求后续将 `gateway/ingest` 改造成 `gateway/subscriber`，并由 Centre Agent 适配候选事件；这些改造不属于本票。

## 工作区

项目组根使用 uv workspace 并维护唯一 `uv.lock`：

```bash
cd sci-weave/centre-control/centre-agents
uv sync
```

运行 Gateway MVP 回归测试：

```bash
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```

各角色只从其本地 `.env` 读取配置；仓库只提交 `.env.example`。Centre Agent 的后续行为规格见工单「最小 Work Agent 实现规格」和 `docs/data-flow/work-agent.md`。
