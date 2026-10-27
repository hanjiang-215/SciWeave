---
id: ai4-zk0g
status: closed
deps: [ai4-yzdd]
links: [ai4-bp6v]
created: 2026-10-22T16:26:48Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-gvan
tags: [audit, centre-control, implementation, enhancement, ready-for-agent]
---
# 写调用先记后做，中断能被检出

## Parent

留痕包改造为接口层调用账本（ai4-gvan）。规格在中央留痕工具共享包实现规格（ai4-tg3v）。

## What to build

写调用先留下 `invoked`，结束后留下配对的 `completed`。只有开头、没有结尾的调用能被找出来。配不上的收尾直接拒绝，不另插一行。账本不可写时写调用跑不起来。收尾时数据库写失败只告警，不把已经发生的业务收回来。上下文管理器包住这一整段，并自己填耗时。

测试只走包的公共接口。先写会失败的测试，再写刚好让它通过的实现。不测内部函数，不模拟包内的协作者。

## Acceptance Criteria

- [x] `begin` 之后能找到未完成调用；`finish` 之后不再出现；两行共用同一个调用标识
- [x] 账本不可写时 `begin` 抛审计库不可用
- [x] `finish` 的数据库写失败不抛，库里留下未配对的 `invoked`
- [x] 没有对应 `invoked`、已经配过、或拿读调用的 `attempted` 去收尾，都抛校验错误，且不另插一行
- [x] 连接上已经开着业务事务时，追加直接报错；干净连接追加后事务已经提交
- [x] 上下文管理器正常结束记 `ok`，里面抛异常则记 `error` 后原样重抛，耗时有值

## Blocked by

- 读调用留下一条并能查回（ai4-yzdd）


## Notes

**2026-10-23T02:25:16Z**

实现与验证：已完成 begin_call/finish_call 两阶段留痕、未完成调用查询、配对校验、审计库不可用时 fail-closed、业务事务保护，以及 call_scope 成功/异常路径和耗时记录。验证命令：在 sci-weave/centre-control/shared/audit-trail 执行 PYTHONPATH=src uv run --with pytest pytest tests -q；14 passed。另执行 uv run python -m compileall -q src tests 与 git diff --check，均通过。

**2026-10-27 复核勾选（hanjiang，按 ai4-bp6v 授权）**

身份核对：复核由 `ai4-bp6v`（assignee hanjiang）执行，本票 assignee 为 Frank Qi，按票面授权「逐条对照现有代码与测试，勾选已满足的验收项」回写，不修改正文。

读代码 + 测试逐条核对（当前 HEAD）：

- AC1（begin 可查未完成、finish 后消失、共用 call_id）：`begin_call` 落 invoked、`find_unfinished_calls` 找 invoked 且无配对 completed；`finish_call` 落 completed；`test_begin_and_finish_share_call_id_and_close_unfinished_call` 断言两行同 id、finish 后 `find_unfinished_calls == []`。✓
- AC2（账本不可写 begin 抛）：`begin_call` 写失败抛 `AuditUnavailableError`（fail-closed）；`test_begin_fails_closed_when_database_is_unavailable` 关闭连接后断言。✓
- AC3（finish 写失败不抛、留下 invoked）：`finish_call` 捕获写失败只记 warning 不抛；复核补齐 `test_finish_write_failure_is_swallowed_and_leaves_invoked`（提交 `c215055`），用锁定库实测：finish 不抛、`find_unfinished_calls` 仍含该 call_id。✓
- AC4（缺 invoked/已配过/attempted 收尾都抛且不插行）：`finish_call` 对三种非法收尾抛 `AuditValidationError`；`test_finish_rejects_missing_duplicate_and_attempted_calls` 覆盖三种并隐含断言不另插行。✓
- AC5（业务事务保护）：写入前检查 `conn.in_transaction`，已开事务则抛 `AuditValidationError`；`test_audit_append_rejects_existing_business_transaction` 断言；干净连接追加后 `test_begin_and_finish_share_call_id...` 能查回，证明已提交。✓
- AC6（call_scope ok/error/耗时）：成功记 `ok`、异常记 `error` 后原样重抛、`duration_ms` 有值；`test_call_scope_records_success_and_reraises_failure` 断言三者。✓

验证命令（复核时实跑）：

```text
cd sci-weave/centre-control/shared/audit-trail
uv run --locked --with pytest python -m pytest tests -q → 16 passed（14 原有 + 2 复核补齐）
python -m compileall -q src tests → 0
git diff --check → 0
```
