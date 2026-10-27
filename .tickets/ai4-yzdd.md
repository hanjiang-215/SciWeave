---
id: ai4-yzdd
status: closed
deps: []
links: [ai4-bp6v]
created: 2026-10-22T16:26:48Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-gvan
tags: [audit, centre-control, implementation, enhancement, ready-for-agent]
---
# 读调用留下一条并能查回

## Parent

留痕包改造为接口层调用账本（ai4-gvan）。规格在中央留痕工具共享包实现规格（ai4-tg3v）。

## What to build

调用方传入路径打开调用账本并建表，记一条读调用，再按原样查回。打不开或建不了表就报审计库不可用，包不自己退出。读调用写入失败只交回空结果，不打断这次读取。

测试只走包的公共接口。先写会失败的测试，再写刚好让它通过的实现。不测内部函数，不模拟包内的协作者。

## Acceptance Criteria

- [x] 不设置环境变量，只传入路径就能打开并建表；连续建表两次仍成功，索引还在
- [x] 记一条读调用后，查询得到一行，阶段是 `attempted`，结果是 `unknown`，摘要和 `refs` 往返不变
- [x] 读调用写入失败时返回空、不抛异常
- [x] 打开或建表失败时抛审计库不可用
- [x] 表的列集合与约定一致，没有入参正文列；内存库建表不因日志模式失败

## Blocked by

None (can start immediately).


## Notes

**2026-10-23T02:25:03Z**

实现与验证：已完成读调用账本公共 API、路径打开与幂等建表、内存库 WAL 降级、attempted 记录及查询回读、审计库不可用时 fail-open。验证命令：在 sci-weave/centre-control/shared/audit-trail 执行 PYTHONPATH=src uv run --with pytest pytest tests -q；14 passed。另执行 uv run python -m compileall -q src tests 与 git diff --check，均通过。

**2026-10-27 复核勾选（hanjiang，按 ai4-bp6v 授权）**

身份核对：复核由 `ai4-bp6v`（assignee hanjiang）执行，本票 assignee 为 Frank Qi，按票面授权「逐条对照现有代码与测试，勾选已满足的验收项」回写，不修改正文。

读代码 + 测试逐条核对（当前 HEAD）：

- AC1（路径打开 + 幂等建表）：`open_connection(path)` 只取路径，不读环境变量；`init_audit_table` 幂等（`CREATE TABLE IF NOT EXISTS` + 索引）；`test_open_and_init_are_path_based_and_idempotent` 断言两次建表成功、`len(indexes) >= 3`。✓
- AC2（attempted 记录可查回）：`record_attempted` 记 phase=`attempted`、result=`unknown`；`test_attempted_call_can_be_read_back_with_digest_and_refs` 断言 args_digest 与 refs 往返不变。✓
- AC3（写入失败返回空不抛）：`record_attempted` 在连接不可用时返回 `None`（fail-open）；`test_attempted_write_is_fail_open` 关闭连接后断言 `is None`。✓
- AC4（打开/建表失败抛不可用）：`open_connection` 对不可写路径抛 `AuditUnavailableError`；`test_open_failure_is_unavailable` 断言。✓
- AC5（列集合无正文列 + 内存库 WAL 降级）：schema 15 列中无 body/args 正文列（复核脚本逐一核对）；`test_open_and_init_are_path_based_and_idempotent` 断言完整列清单，`test_memory_database_downgrades_wal` 断言内存库建表不因 WAL 失败。✓

验证命令（复核时实跑）：

```text
cd sci-weave/centre-control/shared/audit-trail
uv run --locked --with pytest python -m pytest tests -q → 16 passed（14 原有 + 2 复核补齐）
python -m compileall -q src tests → 0
git diff --check → 0
```
