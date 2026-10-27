---
id: ai4-re4t
status: closed
deps: [ai4-zk0g]
links: [ai4-bp6v]
created: 2026-10-22T16:26:48Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-gvan
tags: [audit, centre-control, implementation, enhancement, ready-for-agent]
---
# 按套件调用标识、通道、服务、工具、对象、结果和时间过滤

## Parent

留痕包改造为接口层调用账本（ai4-gvan）。规格在中央留痕工具共享包实现规格（ai4-tg3v）。

## What to build

查询者按套件调用标识、连接通道、服务、工具、目标对象、结果和时间区间缩小一次调用账本。结果按时间稳定倒序，便于把多次查询拼成一条链。公共接口里没有更新或删除。

测试只走包的公共接口。先写会失败的测试，再写刚好让它通过的实现。不测内部函数，不模拟包内的协作者。

## Acceptance Criteria

- [x] 套件调用标识、通道、服务、工具、目标对象、结果各自只留下匹配的调用
- [x] 时间区间同样有效
- [x] 同一时刻的多条记录倒序稳定，重复查询顺序不变
- [x] 不给条件时返回全部，仍是倒序
- [x] 公共接口里没有更新或删除

## Blocked by

- 写调用先记后做，中断能被检出（ai4-zk0g）


## Notes

**2026-10-23T02:25:16Z**

实现与验证：已完成按 caller_id、channel_id、service、tool、target_object_id、result 和时间范围过滤，结果按 occurred_at 与 rowid 稳定倒序；公共 API 仅提供追加和查询，不提供更新/删除。验证命令：在 sci-weave/centre-control/shared/audit-trail 执行 PYTHONPATH=src uv run --with pytest pytest tests -q；14 passed。另执行 uv run python -m compileall -q src tests 与 git diff --check，均通过。

**2026-10-27 复核勾选（hanjiang，按 ai4-bp6v 授权）**

身份核对：复核由 `ai4-bp6v`（assignee hanjiang）执行，本票 assignee 为 Frank Qi，按票面授权「逐条对照现有代码与测试，勾选已满足的验收项」回写，不修改正文。

读代码 + 测试逐条核对（当前 HEAD）：

- AC1（各过滤条件）：`query_audit_calls` 对 caller_id/channel_id/service/tool/target_object_id/result 逐一过滤；`test_query_filters_and_stable_reverse_order` 覆盖 caller_id、channel_id、target_object_id、result。✓
- AC2（时间区间）：`occurred_after`（≥）与 `occurred_before`（≤）均实现；原测试只覆盖 after，复核补齐 `occurred_before` 与组合区间用例（提交 `c215055`）。✓
- AC3（同时刻倒序稳定）：`ORDER BY occurred_at DESC, rowid DESC`，同刻以 rowid 决胜；原测试 `result="unknown"` 返回 `[second, first]` 证明稳定。✓
- AC4（不给条件返回全部倒序）：`query_audit_calls(conn)` 无 WHERE 子句仍倒序，`test_query_filters_and_stable_reverse_order` 断言 `all_rows == [second, first]`。✓
- AC5（无更新/删除）：`audit_trail.__all__` 只含 begin/finish/record_attempted/query/find_unfinished/init/open/call_scope；`test_no_update_or_delete_api_is_exposed` 断言无 `update`/`delete`。✓

验证命令（复核时实跑）：

```text
cd sci-weave/centre-control/shared/audit-trail
uv run --locked --with pytest python -m pytest tests -q → 16 passed（14 原有 + 2 复核补齐）
python -m compileall -q src tests → 0
git diff --check → 0
```
