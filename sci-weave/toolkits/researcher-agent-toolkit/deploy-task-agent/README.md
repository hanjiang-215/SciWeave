# deploy-task-agent

研究员端侧 Task Agent 套件。套件与 `sci-weave/centre-control/centre-agents` 独立，不使用 path 依赖。

## 组成

- `libs/`：状态机投影、Worker Lease、子进程运行边界所需的运行时原语，以及假草稿箱和假队列测试接缝。
- `service-template/`：`gateway/mcp`、`gateway/subscriber`、`worker` 三个服务壳。服务壳只负责启动和装配 libs，不重复实现状态机或租约。
- `agent-definitions/`：可复制的 fast-agent 卡片样例。研究员只能替换这里的 Agent 定义。
- `skills/create-task-agent/`：给 Personal Agent 的操作 skill，只覆盖复制卡片、修改指令和允许的领域 MCP、装入定义槽。
- `systemd/`：Linux 用户级常驻服务单元，分别启动 `gateway/mcp` 和 `gateway/subscriber`。
- `hooks/check-services.sh`：harness 打开时检查并补启动两个用户服务；不会在 harness 关闭时停止服务。

## 本地验证

```bash
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/libs
uv sync
uv run python -m unittest discover -s tests -v
```

测试使用内存状态、假上游交接和假草稿箱，不连接真实队列、真实草稿箱或真实模型。真实部署时由研究员把队列地址、消费者组、SQLite 路径、持久目录、领域 MCP 地址和草稿箱地址填入自己的 `.env`；套件不保存凭据。

## 启动边界

安装两个 systemd 用户服务后执行 `systemctl --user enable --now sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service`。两个 Gateway 进程（`gateway/mcp` 与 `gateway/subscriber`）应由研究员机器上的用户级自启动机制常驻。Personal Agent 打开 harness 时只能检查并补启动，不能在关闭 harness 时停止它们，也不能修改状态机、租约或 Gateway 进程。
