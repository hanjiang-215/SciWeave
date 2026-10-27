# 端到端检查清单

> 本清单按**当前实现**写。哪一条还差什么，直接写在那一行后面——不写「待回填」。
> 最近一次核对：2026-10-27（`ai4-0fwc`、`ai4-u9gj`、`ai4-z3yq` 之后）。

## 假队列验证（不依赖 broker）

1. 向 subscriber 投一条**协调器真实形状**的交接（扁平信封，Kafka key = `f"{task_node_id}:{target_node_version_ref}"`）：
   ```json
   {"message_type": "task_handoff_ready", "task_node_id": "node-1",
    "target_node_version_ref": "cv-1", "target_agent_id": "researcher-1"}
   ```
2. subscriber 读 `task_node_id`（**不是 key**）、写一条 `queued` inbox 行、取得 Worker Lease、拉起 worker 子进程。
3. worker 加载四套配置（`agent-definitions/` / `agent-libs/` / `mcp-libs/` / `workflow-libs/`），跑完这条交接，写草稿箱，`inbox.mark_processed`。
4. subscriber 在 worker **开始跑之前**就提交 offset；崩溃只会留下 `queued` 行，下次启动 `drain_queued()` 重跑。
5. 同一条消息重复投递保持幂等（`dedupe_key` 主键 + `already_processed`）；worker 失败时行留在 `queued`，不写草稿。

推荐命令：`cd runtime && uv run python -m unittest discover -s tests -v`。

### 逐条可核对的证据

| 检查项 | 测试 | 状态 |
| --- | --- | --- |
| 真实信封能读对 `target_id` | `test_subscriber_loop.py::test_target_id_is_the_task_node_not_the_composite_key` | 通过 |
| 同一节点的两个版本各是一条执行 | `test_subscriber_loop.py::test_two_versions_of_one_node_are_two_executions` | 通过 |
| 两个准入守卫真的会触发 | `test_subscriber_loop.py::test_rejects_a_handoff_for_another_agent` / `..._unsupported_integer_schema_version` | 通过 |
| subscriber 真的拉起子进程 | `test_subscriber_loop.py::test_a_real_handoff_through_the_subscriber_starts_the_worker` | 通过 |
| 租约跨进程有效 | `test_worker_dispatch.py::LeaseAcrossProcessesTests` | 通过 |
| 改 YAML 会改变模型收到的 instruction | `test_assembly.py::ConfigurationReachesTheModelTests` | 通过 |
| **模型真的产出答案** | —— | **未验证**：需要真实 `DEEPSEEK_API_KEY`，当前测试全用 passthrough 或替身 |
| **worker 按工作流跑多 Agent** | —— | **未实现**：worker 现在跑单个 agent，`WorkflowExecutor` 已测但未接入，见 `ai4-x0ay` |
| **模型收到的任务文本** | —— | **未实现**：`command_text` 仍是裸 node id，见 `ai4-1e9e` |

## 真实队列验证（可选，本地 Redpanda）

本地 Redpanda 由 `sci-weave/service/redpanda/compose.yaml` 提供。subscriber 在
`QUEUE_URL` 与 `QUEUE_CONSUMER_GROUP` 配置齐全时使用 kafka-python 消费中央队列，
未配置时退回假队列。可用最小脚本验证「生产 → 消费 → 子进程 → offset 提交」：

```python
from kafka import KafkaProducer
from work_agent_runtime import KafkaQueueClient, WorkAgentRuntime, InboxStore, WorkerLease
from work_agent_runtime.worker_dispatch import WorkerSubprocess
import json

producer = KafkaProducer(bootstrap_servers="127.0.0.1:19092", value_serializer=lambda v: json.dumps(v).encode())
producer.send(
    "sciweave.task-handoff.researcher-1",
    key=b"iris-node-1:cv-1",
    value={
        "message_type": "task_handoff_ready",
        "task_node_id": "iris-node-1",
        "target_node_version_ref": "cv-1",
        "target_agent_id": "researcher-1",
        "pending_handoff_id": "p-1",
        "trigger_revision_id": "r1",
    },
).get(timeout=10)

# 与 service-template/gateway/subscriber/src/main.py 的 build_runtime() 同形
runtime = WorkAgentRuntime(inbox=InboxStore("kit.sqlite3"), dispatcher=WorkerSubprocess())
runtime.lease = WorkerLease("kit.sqlite3")
queue = KafkaQueueClient("127.0.0.1:19092", "sciweave.task-workflow.test.researcher", auto_offset_reset="earliest")
queue.subscribe(["sciweave.task-handoff.researcher-1"])
for message in queue.poll(1000):
    envelope = message.payload
    record = runtime.handle_inbound(envelope["task_node_id"], message.key)
    queue.commit()
    print(record.status, record.draft_id)
queue.close()
```

预期：`completed` 且 `draft_id` 非空（passthrough 下是 `draft-<target>-<hex>`，真实模型下是草稿箱返回的 id）；同一 `event_id` 重复投递不产生第二轮执行。
