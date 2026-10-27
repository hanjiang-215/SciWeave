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

- [ ] `begin` 之后能找到未完成调用；`finish` 之后不再出现；两行共用同一个调用标识
- [ ] 账本不可写时 `begin` 抛审计库不可用
- [ ] `finish` 的数据库写失败不抛，库里留下未配对的 `invoked`
- [ ] 没有对应 `invoked`、已经配过、或拿读调用的 `attempted` 去收尾，都抛校验错误，且不另插一行
- [ ] 连接上已经开着业务事务时，追加直接报错；干净连接追加后事务已经提交
- [ ] 上下文管理器正常结束记 `ok`，里面抛异常则记 `error` 后原样重抛，耗时有值

## Blocked by

- 读调用留下一条并能查回（ai4-yzdd）


## Notes

**2026-10-23T02:25:16Z**

实现与验证：已完成 begin_call/finish_call 两阶段留痕、未完成调用查询、配对校验、审计库不可用时 fail-closed、业务事务保护，以及 call_scope 成功/异常路径和耗时记录。验证命令：在 sci-weave/centre-control/shared/audit-trail 执行 PYTHONPATH=src uv run --with pytest pytest tests -q；14 passed。另执行 uv run python -m compileall -q src tests 与 git diff --check，均通过。
