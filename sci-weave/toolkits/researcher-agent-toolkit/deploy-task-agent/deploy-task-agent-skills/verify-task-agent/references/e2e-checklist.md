# 端到端检查清单

## 假队列验证(不依赖 broker)

1. 假队列向 subscriber 投递一个 `event_id` 和 `target_id`。
2. subscriber 将消息交给一个 Worker；Worker 获取一个租约并运行配置工作流。
3. Router、Orchestrator、Parallel 或 Agents as Tools 的子 Agent 在同一执行上下文中完成。
4. 最终写入 Agent 调用假草稿箱恰好一次，结果状态为 `completed`，`draft_id` 非空且唯一。
5. 重复投递同一事件保持幂等；失败子 Agent 不写草稿。

推荐命令：`cd runtime && uv run python -m unittest discover -s tests -v`。

## 真实队列验证(可选,本地 Redpanda)

本地 Redpanda 由 `sci-weave/service/redpanda/compose.yaml` 提供。subscriber 模板在
`QUEUE_URL` 与 `QUEUE_CONSUMER_GROUP` 配置齐全时使用 kafka-python 消费中央队列，
未配置时退回假队列。可用最小脚本验证消息生产→消费→Worker 完成→offset 提交：

```python
from kafka import KafkaProducer
from work_agent_runtime import KafkaQueueClient, WorkAgentRuntime
import json

producer = KafkaProducer(bootstrap_servers="127.0.0.1:19092", value_serializer=lambda v: json.dumps(v).encode())
producer.send("sciweave.task-handoff.researcher-1", key=b"iris-node-1", value={
    "event_id": "demo-2", "event_type": "task_handoff_ready",
    "target": {"kind": "task_node", "id": "iris-node-1"},
    "payload": {"target_agent_id": "researcher-1", "formal_revision_id": "r1", "target_node_version_ref": "nv1"},
}).get(timeout=10)

runtime = WorkAgentRuntime()
queue = KafkaQueueClient("127.0.0.1:19092", "sciweave.task-workflow.test.researcher", auto_offset_reset="earliest")
queue.subscribe(["sciweave.task-handoff.researcher-1"])
for message in queue.poll(1000):
    target_id = (message.payload.get("target") or {}).get("id")
    execution = runtime.handle_message(target_id, message.payload.get("event_id"))
    queue.commit()
    print(execution.status, execution.draft_id)  # completed + 非空 draft_id
queue.close()
```

预期：`completed` 且 `draft_id` 非空；同一 `event_id` 重复投递不产生第二轮执行。