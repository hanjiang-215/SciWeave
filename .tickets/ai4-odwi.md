---
id: ai4-odwi
status: closed
deps: []
links: []
created: 2026-10-29T01:43:38Z
type: bug
priority: 0
assignee: hanjiang
---
# subscriber task_completed 提交后 best-effort 发布可丢失

技术审查 P0-1：worker_runner.py:204-218 完成终态提交后才发布 task_completed，崩溃间隙事件永久丢失，下游节点永不释放。

## Acceptance Criteria

改为 outbox：同事务写待发事件，独立 relay 补发并标记；测试覆盖崩溃恢复补发。
## Notes

2026-10-29 hanjiang：已修复，提交 a1ddb9。

- worker/store.py 新增 governance_outbox 表（dedupe_key 唯一）与 ecord_outbox_event / pending_outbox_events / mark_outbox_published / mark_outbox_failed。
- worker_runner._persist 在写完成终态的**同一事务**内落 task_completed 事件；提交后 drain_outbox() 补发，un_once() 开头也先补发，崩溃后下一轮自愈。
- KafkaCompletionPublisher.publish 改为严格：等待 send future，未确认即抛 CompletionPublishError，避免把“未送达”记成已发布。

验证：subscriber 33 passed，其中 CompletionOutboxTests 覆盖“broker 挂→事件留存→恢复后仅补发一次”。

遗留风险：outbox 只在完成态路径写入；relay 依赖消费循环驱动，无独立定时线程。