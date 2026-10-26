---
id: ai4-ze1x
status: closed
deps: []
links: [ai4-dybh]
created: 2026-10-22T01:23:36Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-tg3v
tags: [audit, shared, ready-for-agent]
---
# 审计写入面：标准表与只追加写入接口

## Parent

[中央留痕工具共享包实现规格](ai4-tg3v.md)

## What to build

调用方在自己的 SQLite 事务内调用写入函数，能成功追加一条审计事件；不在事务内调用被明确拒绝；字段缺失或枚举非法被拒；event_id 与 occurred_at 由包生成。交付共享包骨架、标准审计表、事件模型与回归测试。

## Acceptance criteria

- [x] 在事务内写入成功，提交后可按 event_id 读回
- [x] 不在事务内调用抛 TransactionRequiredError；非 sqlite3.Connection 被拒
- [x] 必填字段缺失、actor_type/operation 枚举非法抛 AuditValidationError
- [x] 无 update/delete 公共 API
- [x] event_id 为 UUID4、occurred_at 为 UTC ISO8601，调用方不可传入覆盖
- [x] 回归测试全绿（uv run python -m unittest discover）

## Notes

**2026-10-22T00:00:00Z**

实现完成：`sci-weave/shared/audit-trail/` 交付写入面（标准表、事件模型、`write_audit_event`、`init_audit_table`）与查询面所需的最小包骨架。测试 `uv run python -m unittest discover -s tests` 11 项全绿；`git diff --check` 通过。事务外写入抛 `TransactionRequiredError`，字段/枚举非法抛 `AuditValidationError`；`event_id` UUID4、`occurred_at` UTC 微秒精度，均由包生成。查询面见 ai4-rh97。

## Blocked by

None (can start immediately)


**2026-10-22T15:31:08Z**

2026-10-22 作废说明（本票保持关闭，正文不删）。

本票交付的存储层写入面已从 sci-weave/centre-control/shared/audit-trail 删除，包括 audit_event、write_audit_event、AuditEvent、Operation、TransactionRequiredError。不得按本票把这套接口加回去。

后续只按「留痕包改造为接口层调用账本」(ai4-gvan) 重写调用账本。规格仍是「中央留痕工具共享包实现规格」(ai4-tg3v)。
