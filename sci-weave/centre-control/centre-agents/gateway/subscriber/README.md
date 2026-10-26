# Centre Agent Gateway Subscriber

中央 Centre Agent 的队列订阅器:出站连接消息队列,按目标 TaskNode/候选事件订阅,收到消息即持久化 `queued` 执行记录并驱动 Worker。它是 `gateway/mcp`(处置面)之外的第二个常驻入口,与 mcp 共享同一份 SQLite 与状态机。

## 职责

- 订阅器的价值在于长期持有 consumer group 与 offset:同一 Agent 的多个实例共享消费者组竞争消费,重新上线继续消费未提交 offset。
- 消息到达 → 单个事务创建 `queued` ExecutionRecord(`trigger=queue`、`trigger_ref` 记消息标识)+ 审计事件。
- Worker 侧原子领取该目标的 Worker Lease,领到才运行;同一目标串行、跨目标可并发;重复投递由 business key 唯一约束挡住。
- offset 在整轮 Worker 运行完结后提交;崩溃重启会重放,重复由业务键幂等挡住,不追求精确一次。

## 本地验证

```bash
cd sci-weave/centre-control/centre-agents
uv sync
uv run --package sciweave-task-agent-gateway-subscriber \
  python -m unittest discover -s gateway/subscriber/tests -v
```

测试使用假队列与确定性运行时,不连接真实 Redpanda、不调用真实模型、不使用固定端口。

## 运行

队列 bootstrap 与消费者组都配置时使用真实 Redpanda(kafka-python);任一为空时退回 `FakeQueueClient`(仅本地演示/测试):

```bash
uv run --env-file .env --package sciweave-task-agent-gateway-subscriber \
  sciweave-task-agent-gateway-subscriber
```

所有路径、地址、端口、令牌、数据库位置与 Worker 运行目录由环境变量配置,仓库只提交 `.env.example`。草稿箱写入仅当配置了 `SCIWEAVE_DRAFT_BUFFER_ENDPOINT` 时启用,完成后状态保存 `draft_id`;写入失败记为 `failed` 且错误码 `draft_submission_failed`。

## 不做的事

- 不提供 MCP 工具、不承接任务下发、不写正式版本、不自动重做 `failed` 记录。
- 不以订阅器覆盖领域管理 MCP 的治理边界;topic 与 business key 只做去重与路由,不替代 `executor_refs` 授权。