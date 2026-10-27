---
id: ai4-rh97
status: closed
deps: [ai4-ze1x]
links: [ai4-dybh]
created: 2026-10-22T01:23:42Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-tg3v
tags: [audit, shared, ready-for-agent]
---
# 审计查询面：按任务/Proposal/正式版本/时间重建

## Parent

[中央留痕工具共享包实现规格](ai4-tg3v.md)

## What to build

只读查询函数按 task_id / proposal_id / formal_revision_id / 时间区间过滤，时间倒序返回事件，能重建「谁在什么基准上做了什么、结果如何、谁批准」；refs JSON 往返无损。含回归测试。

## Acceptance criteria

- [x] 按 task_id / proposal_id / formal_revision_id 过滤得到正确子集
- [x] 按 occurred_after / occurred_before 过滤正确，结果时间倒序
- [x] refs 写入 JSON 后读回等值
- [x] 全部 operation 枚举可写可查
- [x] 回归测试全绿（uv run python -m unittest discover）

## Notes

**2026-10-22T00:00:00Z**

实现完成：`query_audit_events(conn, *, task_id, proposal_id, formal_revision_id, occurred_after, occurred_before)` 只读查询，按时间倒序（`occurred_at DESC, rowid DESC` 稳定排序）返回事件 dict；`refs` JSON 往返无损。测试 11 项全绿（含本票全部验收场景），`git diff --check` 通过。依赖 ai4-ze1x 的标准表结构。

## Blocked by

审计写入面：标准表与只追加写入接口


**2026-10-22T15:31:08Z**

2026-10-22 作废说明（本票保持关闭，正文不删）。

本票交付的按任务、Proposal、正式版本过滤的查询面，随旧写入面一起删除。不得按本票恢复 query_audit_events 或那些领域字段过滤。

后续查询以调用者、通道、服务、工具、目标对象、结果和时间为准，实现仍在「留痕包改造为接口层调用账本」(ai4-gvan)。
