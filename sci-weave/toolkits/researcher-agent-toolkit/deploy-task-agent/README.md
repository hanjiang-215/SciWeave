# deploy-task-agent

研究员端 Task Agent 套件，按目标交付结构组织：

- `runtime/`：状态记录、Worker Lease、配置模型、资源注册表和单 Worker 多 Agent 工作流。
- `service-template/`：`gateway/subscriber` 是已实现的常驻消费者；`gateway/mcp` 是研究员处置面，提供 `docs/data-flow/work-agent.md` 的六个工具（`health`/`query_execution`/`list_pending`/`cancel_execution`/`answer_question`/`review_execution`），读写与 subscriber 共用的 SQLite 执行库；`worker` 是一次性执行壳，用 `build_agent_runtime()` 装配真实 fast-agent 运行时，把队列里的一条执行跑完并写入草稿箱；缺 Key 启动即失败，passthrough 仅在 `SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1` 时可用。
- `agent-definitions/`：兼容入口的 Agent 定义、schema；可复用 Workflow 资源位于 `libs/workflow-libs/`。
- `libs/agent-libs/`：纯 YAML/JSON/Markdown Agent 行为资源，由 runtime 加载。
- `libs/mcp-libs/`：纯 JSON/YAML MCP 工具描述资源，由 runtime 加载。
- `libs/workflow-libs/`：纯 YAML Workflow 协议、schema 和四类工作流示例。
- `libs/local-agent-libs/`、`libs/local-mcp-libs/`：研究员自定义资源配置。
- `custom-mcp/`：需要 Python 实现的自定义 MCP 服务，每个服务是独立 uv 子项目。
- `hooks/`、`systemd/`：harness 检查和用户级常驻服务。

套件与 `sci-weave/centre-control/centre-agents` 独立，不使用 path 依赖。Personal Agent 只能修改 Agent 定义、工作流声明和资源配置，不能修改 runtime、Worker Lease、Gateway 或服务模板。

## 本地验证

```bash
cd runtime
uv sync
uv run python -m unittest discover -s tests -v
```

Agent、MCP、Workflow libs 是纯配置资源，不单独执行 `uv sync`；由 runtime 通过 `AGENT_LIBS_PATH`、`MCP_LIBS_PATH`、`WORKFLOW_LIBS_PATH` 或显式路径加载。
测试使用内存状态、假上游交接和假草稿箱，不连接真实队列、真实草稿箱或真实模型。真实地址、令牌和本地扩展路径只通过环境变量配置；仓库只提交 `.env.example`。

## 启动三个角色

`service-template/` 下的三个角色**不各自维护 `pyproject.toml`**：它们与 `runtime/` 同处一个 uv 项目，靠 `--project runtime` 借用 runtime 的已安装 `work_agent_runtime` 与依赖，因此只需 `runtime/` 里执行过一次 `uv sync`。

```bash
cd runtime
uv run --env-file .env python ../service-template/gateway/subscriber/src/main.py
uv run --env-file .env python ../service-template/gateway/mcp/src/main.py
uv run --env-file .env python ../service-template/worker/src/main.py
```

三个角色缺配置时**启动即失败**并指名缺哪一项，不会退化成一个空转进程：

| 角色 | 缺配置时的报错 |
| --- | --- |
| `gateway/subscriber` | `SCIWEAVE_AGENT_ID must be configured through the environment` |
| `gateway/mcp` | `DATABASE_PATH must be configured through the environment` |
| `worker` | `DATABASE_PATH must be configured through the environment`（配好数据库后还需要模型凭据） |

`service-template` 是研究员可见的模板：Personal Agent 只能改 Agent 定义、工作流声明与资源配置，不能改这三个角色与 `runtime/`。

## 队列消费启动（subscriber）

`service-template/gateway/subscriber` 是常驻消费者：出站连接中央 Redpanda 队列，
把 `task_handoff_ready` 交给 runtime 驱动 Worker，消息处理完整后才提交 offset。
`QUEUE_URL` 与 `QUEUE_CONSUMER_GROUP` 配置齐全时用真实 kafka-python 客户端；任一
为空时退回假队列（本地演示/测试）。子主题为 `sciweave.task-handoff.<agent_id>`，
已在 `.env.example` 说明。真实链路最小验证见
`deploy-task-agent-skills/verify-task-agent/references/e2e-checklist.md`。

### Inbox 与重启恢复

配置 `DATABASE_PATH` 后，subscriber 先把每条入站消息写入 SQLite Inbox 再驱动执行：

- 缺少 Workflow binding 的消息保持 `awaiting_workflow_binding`，不产生执行；
  binding 建立（`runtime.bind`）后转为 `queued` 再执行；
- 重复投递按 `dedupe_key` 幂等，不产生第二轮执行；
- 订阅器启动时先 `drain_queued()` 重放上次运行遗留的 `queued` 行，崩溃不吞消息。

### 草稿写入

配置 `DRAFT_BUFFER_MCP_URL` 与 `DRAFT_BUFFER_MCP_TOKEN` 后，执行结果写入真实中央草稿箱
（Streamable HTTP `create_draft`）；任一为空时使用假草稿箱（本地演示/测试）。
领域命名空间由 `SCIWEAVE_DRAFT_NAMESPACE` 指定（默认 `mapping`）。端点、令牌与命名空间
全部来自环境变量，仓库不持有真实凭据。

## 启动边界

安装 systemd 用户服务后执行 `systemctl --user enable --now sciweave-task-agent-subscriber.service`。`sciweave-task-agent-mcp.service` 需要 `DATABASE_PATH` 与 `DISPOSITION_MCP_TOKEN`，未配置时启动即失败。打开 harness 时只执行 `hooks/check-services.sh` 检查并补启动；关闭 harness 不停止用户级常驻服务。
