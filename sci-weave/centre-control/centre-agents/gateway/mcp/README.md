# Centre Agent Gateway MCP

中央 Centre Agent 的常驻 MCP 控制面：把「有人需要看一眼」「有人在等一个答案」这两类状态
暴露给人和外部调度，同时提供执行记录与审计的读取面。

## 当前入口

- 候选事件由 `gateway/ingest` 接收并交给 Gateway；测试使用假队列直接调用候选事件入口。
- `POST /mcp` 需要 `Authorization: Bearer <token>`。
- MCP 提供 `query_execution`、`cancel_execution`、`list_pending`、`answer_question`、
  `review_execution` 和 `health`。
- 不提供 `submit_owner_command`，也不提供 `accept`；任务触发来自候选事件，而不是 Owner MCP 命令。

## 处置面不是占位

`answer_question` 与 `review_execution` 曾长期返回 `unimplemented`。那时的 MCP 只能看、不能推进：
一个停在 `waiting` 的执行没有任何入口能被解开。现在两者都落库，实现在
`worker/src/task_agent_worker/store.py`：

| 动作 | 状态迁移 | 关键点 |
| --- | --- | --- |
| `ask_question`（worker 侧） | `queued`/`running` → `waiting` | 写入 `pending_question`，执行停在这里等人 |
| `answer_question` | `waiting` → `completed`，并新建一条 `queued` 的 `resume_of` 记录 | 不是把原记录改回运行，而是**新建一条续跑执行**指回原执行 |
| `review_execution` | 只接受 `accepted` / `rejected` | 与研究员侧的处置契约一致 |

三个容易踩的点：

1. **`answer_question` 靠 `idempotency_key` 幂等。** 重复提交同一个 key 返回第一次的
   `execution_id` 且 `idempotent=true`，不会产生第二条续跑。没有 key 就没有幂等——那时重试
   会真的再跑一次。
2. **续跑是一条新执行，不是原执行复活。** 原记录的 `status` 变成 `completed`、
   `pending_question` 被清空；新记录 `trigger=resume`、`resume_of=<原 execution_id>`、
   `business_key=answer:<idempotency_key>`。查历史时要顺着 `resume_of` 走，否则会以为
   那次执行莫名其妙地「完成了」。
3. **状态不对就拒绝，不猜。** 对一个 `completed` 的执行调 `answer_question` 得到
   `invalid_state`，对一个不存在的执行得到 `not_found`。这两种不是故障，是叫人别把
   已经结束的事再说一遍。

## 这个面里没有的东西

- 没有派发：派发根任务在协调服务的 MCP 上，其余由候选事件驱动。
- 没有预审写入：`append_prereview_log`、`create_merged_candidate` 在领域管理 MCP 上，
  由中央 Agent 用 `centre` 能力调用。
- 没有正式化：正式化是 Project Owner 的动作。

## 本地验证

```bash
cd sci-weave/centre-control/centre-agents
uv sync
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
uv run --package sciweave-task-agent-worker \
  python -m unittest discover -s worker/tests -v
```

服务路径、令牌、数据库位置和 Worker 运行目录由环境变量配置；仓库只提交 `.env.example`。
测试使用临时 SQLite、系统分配端口和固定占位运行时，不连接真实队列或模型。
