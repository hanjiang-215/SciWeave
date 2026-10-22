# SciWeave audit-trail

中央服务留痕工具：所有改动正式事实的组件共用的一套固定审计接口。契约见 `.tickets/ai4-upsm.md`。

## 定位

- 统一发生在**接口层**，不在存储层：Mapping、Wiki、Buffer 各自持有审计 SQLite，分别落库。
- 只追加，不提供更新或删除；写入口与查询入口分离。
- 写入必须发生在调用方自己的 SQLite 事务内，独立调用被拒绝。

## 使用

```python
import sqlite3
from audit_trail import AuditEvent, init_audit_table, write_audit_event

conn = sqlite3.connect("governance.sqlite3")
init_audit_table(conn)

event = AuditEvent(
    actor_id="researcher-1",
    actor_type="human",
    operation="draft.status_changed",
    target_object_type="draft",
    target_object_id="draft-42",
    result="accepted",
    proposal_id="proposal-1",
)

with conn:
    write_audit_event(conn, event)
```

- `event_id`（UUID4）与 `occurred_at`（UTC ISO8601）由包生成，调用方不传。
- 不在事务内调用抛 `TransactionRequiredError`；字段缺失或枚举非法抛 `AuditValidationError`。

## 事件字段

必填：`actor_id`、`actor_type`（`human`/`agent`/`system`）、`operation`、`target_object_type`、`target_object_id`、`result`。

可选：`previous_state`、`next_state`、`reason`、`base_revision`、`candidate_revision`、`proposal_id`、`task_id`、`resource_id`、`formal_revision_id`、`merge_request_id`、`refs`（JSON 兜底）。

`operation` 首版枚举：

| operation | 写入方 |
| --- | --- |
| `draft.status_changed` | 草稿箱 Buffer |
| `mapping.prereview_log_appended` | Mapping 管理 MCP |
| `mapping.formal_revision_promoted` | Mapping 管理 MCP |
| `wiki.prereview_log_appended` | Wiki 管理 MCP |
| `wiki.formal_revision_promoted` | Wiki 管理 MCP |

## 查询

```python
from audit_trail import query_audit_events

rows = query_audit_events(conn, task_id="task-a", occurred_after="2026-01-01T00:00:00+00:00")
```

按 `task_id` / `proposal_id` / `formal_revision_id` / 时间区间过滤，时间倒序返回事件 dict 列表。

## 开发

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

只依赖 Python 标准库。
