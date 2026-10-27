# deploy-task-agent

研究员端 Task Agent 套件，按目标交付结构组织：

- `runtime/`：状态记录、Worker Lease、配置模型、资源注册表和单 Worker 多 Agent 工作流。
- `service-template/`：`gateway/subscriber` 是常驻消费者，持有 Worker Lease 并在拿到交接后拉起**一次性 worker 子进程**；`gateway/mcp` 是研究员处置面，提供 `docs/data-flow/work-agent.md` 的六个工具（`health`/`query_execution`/`list_pending`/`cancel_execution`/`answer_question`/`review_execution`），读写与 subscriber 共用的 SQLite 执行库；`worker` 是被拉起的那一端，用 `build_agent_runtime()` 装配真实 fast-agent 运行时、跑完一条交接并写入草稿箱（凭据只在这里），缺 Key 启动即失败，passthrough 仅在 `SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1` 时可用。
- `agent-definitions/`：**Agent 定义的出处**。`agents/*.yaml` 写 `identity` / `instruction` / `model` / `allowed_mcp_resources`，由 `build_agent_runtime()` 加载；`schema.yaml` 是结构约束。工作流声明不在这里，见 `libs/workflow-libs/`。
- `libs/agent-libs/`：Agent **引用**的行为资源（`prompt` / `formatter` / `task_mode` / `validator` / `workflow_helper`），按 `名字@版本` 被定义的 `resources:` 列表引用。与 `agent-definitions/` 是两种东西：前者是 agent 本身，后者是 agent 引用的材料，因此两个目录都保留。
- `libs/mcp-libs/`：纯 JSON/YAML MCP 工具描述资源，由 runtime 加载。
- `libs/workflow-libs/`：纯 YAML Workflow 协议、schema 和四类工作流示例。
- `libs/local-agent-libs/`、`libs/local-mcp-libs/`：研究员自定义资源配置。
- `custom-mcp/`：需要 Python 实现的自定义 MCP 服务，每个服务是独立 uv 子项目。
- `hooks/`、`systemd/`、`install.sh`：harness 检查、用户级常驻服务与安装脚本；`bin/` 是两个服务的入口。

套件与 `sci-weave/centre-control/centre-agents` 独立，不使用 path 依赖。Personal Agent 只能修改 Agent 定义、工作流声明和资源配置，不能修改 runtime、Worker Lease、Gateway 或服务模板。

## 配置是怎么进到运行时的

四套目录全部在 worker 启动时加载，入口是 `work_agent_runtime.assembly.load_worker_config()`：

| 目录 | 环境变量 | 加载成 | 失败时 |
| --- | --- | --- | --- |
| `agent-definitions/agents/` | `AGENT_DEFINITIONS_PATH` | `AgentDefinition`（instruction / model / 允许的 MCP） | 启动失败 |
| `libs/agent-libs/` | `AGENT_LIBS_PATH` | `AgentResource` 注册表 | 启动失败 |
| `libs/mcp-libs/` | `MCP_LIBS_PATH` | `MCPRegistry` | 启动失败 |
| `libs/workflow-libs/` | `WORKFLOW_LIBS_PATH` | `WorkflowDefinition` | 启动失败 |

四者都有出厂默认（相对套件根目录），所以不设变量也能跑。`SCIWEAVE_AGENT_ID` 决定**用哪一个 agent 定义**——它同时决定订阅的 topic，一个身份贯穿整套。变量留空时用套件自带目录；指错路径或定义不合法时 worker 拒绝启动，并指出是哪个变量、哪个目录。

改完 YAML 后 `bin/start-subscriber` 不需要重启（worker 是一次性进程，每条交接重新装配），`systemctl --user restart sciweave-task-agent-subscriber.service` 只在改了 `.env` 时需要。

## 安装与启动边界

```bash
./install.sh            # 装到 ~/.sciweave/task-agent 并注册两个用户服务
vi ~/.sciweave/task-agent/.env
systemctl --user enable --now sciweave-task-agent-subscriber.service
```

`install.sh` 幂等：重复执行只更新代码，保留已有的 `.env`、`WORKER_HOME` 与 SQLite 文件。装到别处用 `SCIWEAVE_TASK_AGENT_HOME=/path ./install.sh`，单元文件里的路径会同步替换。

两个服务的入口是 `bin/start-subscriber` 与 `bin/start-mcp`，都从套件根目录解析路径并跑在 `runtime/` 的 uv 环境里——`work_agent_runtime` 只装在 runtime 项目里，`service-template/` 下没有第二份。缺 `.env` 时立即退出并说明原因。

`sciweave-task-agent-mcp.service` 还需要 `DATABASE_PATH` 与 `DISPOSITION_MCP_TOKEN`，未配置时启动即失败。

打开 harness 时执行 `hooks/check-services.sh` 检查并补启动；关闭 harness 不停止用户级常驻服务。未安装时该 hook 打印跳过原因并正常退出，不阻断 harness 启动。

## 一次交接的完整路径

```
Redpanda topic
  └─ subscriber  run_loop         读信封 -> target_id / event_id
       ├─ inbox.enqueue           写 queued 行（dedupe_key 幂等，含任务文本）
       ├─ WorkerLease.acquire     SQLite 持久锁，跨进程有效
       ├─ 拉起 worker 子进程       service-template/worker/src/main.py --dedupe-key <key>
       │    └─ build_agent_runtime -> 加载四套配置 -> fast-agent
       │         └─ 调模型 -> 写草稿箱 -> inbox.mark_processed
       └─ queue.commit            **不等 worker 跑完**
```

三点值得单独说明：

- **offset 在 worker 开始跑之前就提交。** 模型调用可能比轮询长得多，把 offset 押到模型返回，重启后整批消息会重放而 inbox 去重又把它们全挡掉——那是比丢一条更糟的状态。现在崩溃只会留下一条 `queued` 行，下次启动 `drain_queued()` 重跑。
- **Worker Lease 是 SQLite 里的一行，不是内存里的 `set`。** 内存在子进程模型下等于没有锁。租约在拉起子进程**之前**取得、跑完之后释放，期间同一 TaskNode 的第二次投递会被拒绝。租约带 TTL（默认 1800 秒），被 `kill -9` 的 subscriber 不会永久占住一个节点。
- **subscriber 不持有草稿箱凭据。** 草稿由 worker 通过 `draft-buffer` MCP 写入（见 `ai4-z3z4`、`ai4-4zjz`）；subscriber 里出现 `DRAFT_BUFFER_MCP_TOKEN` 就说明边界被破坏了。

`DATABASE_PATH` 未设置时没有持久 inbox，子进程也无行可跑，此时 subscriber 退回内联模式并打印一行提示——这是显式降级，不是静默回退。`SCIWEAVE_WORKER_DISPATCH=0` 是另一种：subscriber 只入队、不派发，把行留给独立部署的 worker 服务（`LeaveQueued`），**不是**回退到内联——回退会写一份编造的草稿并把行标成已完成，正好与「分成两个服务」相反。

### 模型收到的那句话从哪来

`inbox_messages.command_text`（`ai4-1e9e`）。subscriber 从信封里按若干候选字段名读任务文本，读不到就存空串——空串是事实，不是失败。worker 侧的 `task_instruction()` 把空串变成一句显式的说明（「本条交接没有任务指令，只收到节点引用，不要从标识符推断任务」），**不再**回退成 `target_id`。

那个回退曾经存在，代价是：模型拿到 `"node-2"`，从名字里编出一个任务，返回一份看起来完整的草稿，于是没人发现载荷是空的。现在没有任务文本时，草稿会明说它不知道要做什么。

真实信封里现在**没有**任务文本字段（`ai4-derq` 在裁信封形状），所以接生产后模型会收到那句说明，直到生产端开始发任务文本。这是刻意选择的可见失败。

### 多 Agent 工作流

`SCIWEAVE_WORKFLOW` 指定跑哪一个工作流（`libs/workflow-libs/` 里的名字）。留空时，**只有一个**工作流的配置会直接跑那个；套件自带五个（一个是预设、四个是 fast-agent 的写法样例），所以出厂要在 `.env` 里写：

```bash
SCIWEAVE_WORKFLOW=literature-agent
```

预设 `literature-agent` 是「一个编排器 + 三个只读 reader + 一个写作者」：

| agent | fast-agent 类型 | 挂的卡 | 职责 |
| --- | --- | --- | --- |
| `literature-agent` | `orchestrator` | **无** | 拆解调研、派活、汇总；不写草稿 |
| `literature-searcher` | `agent` | `literature-search` | 联网检索、读摘要 |
| `literature-mapping-reader` | `agent` | `research-mapping` | 读 TaskNode、取 `task_owner_id` |
| `literature-wiki-reader` | `agent` | `research-wiki` | 查已有正式词条 |
| `literature-draft-writer` | `agent` | `draft-buffer` + `email-service` | 写草稿、发通知、回传 `draft_id` |

**为什么一定要拆成子 agent：** `fast_agent/core/direct_decorators.py` 里 `orchestrator` 与 `parallel` 把 `servers` 硬编码成空列表（注释是 “Orchestrators don't connect to servers directly”），`router` 与 `agent` 才接受 `servers`。所以编排器拿不到 `create_draft`，写草稿的能力只能挂在子 agent 上。这条约束在 `runtime/tests/test_workflow_agent.py` 里有一条断言钉着：`literature-agent` 的 `allowed_mcp_resources` 必须是空元组。

每一步都**按该 agent 的定义单独装配一个 runtime**（`WorkerConfig.with_agent`），不是共用一个：instruction、model、`allowed_mcp_resources` 都是逐 agent 的，共用会把三个 reader 的指令发给同一个 agent，并把写作者的 `create_draft` 交到 reader 手里。代价是每步写一次 `fast-agent.yaml`——一次文件写，不是一次模型调用。

`final_writer` 由 runtime 在编排结束后**确定性地调一次**，不看 plan 里有没有它：模型可能规划出「检索、读、完」，那样就没人生成草稿，而 plan 本身看起来毫无问题。这一步是真实的模型调用（把结论改写成草稿署名格式），四类工作流都会多这一次，`Router` 与 `Agents as Tools` 那一次不产出新信息。

### 草稿与通知的归属

写作者有 `draft-buffer` 卡，所以**草稿由它写**，runtime 只接收它回传的 id：

```json
{"draft_id": "<create_draft 返回的 uuid>", "summary": "<一句话结论>"}
```

runtime 用 `json.loads` 解析（容忍代码块围栏）并校验是规范 UUID；解析失败或非 UUID 记 `draft_id_missing` 并让执行 `failed`，**不写伪造的 id**。这种 id 是 agent 的自述、runtime 没有独立验证过，所以落库时带 `draft_id_source: "agent_reported"`，`query_execution` 一并返回——不要把它当成「runtime 验过」。

写作者没有 `draft-buffer` 卡时，runtime 自己写草稿并读回 id，此时标记是 `runtime`。判断依据是 agent 自己的 `allowed_mcp_resources`，不是额外的 YAML 开关：多一个布尔值就多一处能和卡片互相矛盾的地方。

通知同理，由写作者通过 `email-service` 发，但三个字段是 runtime 的账、由 `notifications.notification_brief()` 原样交给它：`dedupe_key`（`draft-ready:<execution_id>`，重放只发一次）、`related`（含 `execution_id` / `task_node_id`）、`schema_version`（**字符串** `"1"`，整数会被服务端拒绝）。`recipients` 的 `principal_id` 用 agent 从映射里读到的 `task_owner_id`——runtime 不知道谁是负责人，编一个就是把邮件发给陌生人。`notification_kind` 只有 `draft_ready` 可用（`CONFIGURED_NOTIFICATION_KINDS` 是封闭的 13 个值，没有 `task_agent_run_finished`）。

通知失败**不让整轮失败**：写作者同时持有两张卡，通知失败发生在草稿写成之后，为了一封没发出去的邮件丢掉一份已经写好的草稿不划算。错误码由 agent 放进回答的可选字段 `notification_error`，runtime 转述到 worker 的 stdout 行里。它和 `draft_id_source` 一样是转述，不是 runtime 亲自确认过的事实。

`notifications.notification_problem()` 在本地按 `_content_problem` 的四条硬规则（长度、HTML、控制字符、`related` 是对象）预检一遍，只是为了让研究员看到「subject 超了 40 个字」而不是服务端一句 `invalid`；服务端仍是权威，这个预检不能用来跳过调用。

## 本地验证

```bash
cd runtime
uv sync
uv run python -m unittest discover -s tests -v
```

Agent、MCP、Workflow libs 是纯配置资源，不单独执行 `uv sync`；由 runtime 通过 `AGENT_LIBS_PATH`、`MCP_LIBS_PATH`、`WORKFLOW_LIBS_PATH` 或显式路径加载。
包内三对变量一一对应：`AGENT_LIBS_PATH` / `LOCAL_AGENT_LIBS`、`MCP_LIBS_PATH` / `LOCAL_MCP_LIBS`、`WORKFLOW_LIBS_PATH` / `LOCAL_WORKFLOW_LIBS_PATH`。前者指出厂标准目录，后者指研究员自己的目录，同名定义本地覆盖标准；本地目录为空或不设都表示「没有覆盖」，标准目录缺失才报错。
测试使用内存状态、假上游交接和假草稿箱，不连接真实队列、真实草稿箱或真实模型。真实地址、令牌和本地扩展路径只通过环境变量配置；仓库只提交 `.env.example`。

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

草稿由 **Worker 里的 agent** 通过草稿箱 MCP 服务器写，不由订阅端写。订阅端（`gateway/subscriber`）不持有草稿箱凭据、也不读 `DRAFT_BUFFER_MCP_URL` / `DRAFT_BUFFER_MCP_TOKEN`：它只驱动状态机，两处都写会让同一轮执行产出两份草稿。

`worker/src/main.py` 装配 `BufferMCPDraftWriter`，读 `DRAFT_BUFFER_MCP_URL` 与 `DRAFT_BUFFER_MCP_TOKEN`（Streamable HTTP `create_draft`）；任一为空时使用假草稿箱（本地演示/测试）。领域命名空间由 `SCIWEAVE_DRAFT_NAMESPACE` 指定（默认 `mapping`）。端点、令牌与命名空间全部来自环境变量，仓库不持有真实凭据。
