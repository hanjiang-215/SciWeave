# deploy-task-agent

研究员端 Task Agent 套件，按目标交付结构组织：

- `runtime/`：状态记录、Worker Lease、配置模型和单 Worker 多 Agent 工作流。
- `service-template/`：`gateway/mcp`、`gateway/subscriber`、`worker` 三个启动壳。
- `agent-definitions/`：Agent 定义、四类工作流示例和 schema。
- `libs/libs/agent-libs/`：标准 Agent 行为资源。
- `libs/libs/mcp-libs/`：标准 MCP 工具描述资源。
- `local-libs/agent-libs/`、`local-libs/mcp-libs/`：研究员自定义资源占位与说明。
- `deploy-task-agent-skills/`：创建、编排、配置 MCP、验证和排障技能组；每个技能带自己的 `references/`。
- `hooks/`、`systemd/`：harness 检查和用户级常驻服务。

套件与 `sci-weave/centre-control/centre-agents` 独立，不使用 path 依赖。Personal Agent 只能修改 Agent 定义、工作流声明和资源配置，不能修改 runtime、Worker Lease、Gateway 或服务模板。

## 本地验证

```bash
cd runtime
uv sync
uv run python -m unittest discover -s tests -v
cd ../agent-libs
uv sync
uv run python -m unittest discover -s tests -v
cd ../mcp-libs
uv sync
uv run python -m unittest discover -s tests -v
```

测试使用内存状态、假上游交接和假草稿箱，不连接真实队列、真实草稿箱或真实模型。真实地址、令牌和本地扩展路径只通过环境变量配置。

## 启动边界

安装两个 systemd 用户服务后执行 `systemctl --user enable --now sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service`。打开 harness 时只执行 `hooks/check-services.sh` 检查并补启动；关闭 harness 不停止用户级常驻服务。
