---
id: ai4-re4t
status: closed
deps: [ai4-zk0g]
links: []
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

- [ ] 套件调用标识、通道、服务、工具、目标对象、结果各自只留下匹配的调用
- [ ] 时间区间同样有效
- [ ] 同一时刻的多条记录倒序稳定，重复查询顺序不变
- [ ] 不给条件时返回全部，仍是倒序
- [ ] 公共接口里没有更新或删除

## Blocked by

- 写调用先记后做，中断能被检出（ai4-zk0g）


## Notes

**2026-10-23T02:25:16Z**

实现与验证：已完成按 caller_id、channel_id、service、tool、target_object_id、result 和时间范围过滤，结果按 occurred_at 与 rowid 稳定倒序；公共 API 仅提供追加和查询，不提供更新/删除。验证命令：在 sci-weave/centre-control/shared/audit-trail 执行 PYTHONPATH=src uv run --with pytest pytest tests -q；14 passed。另执行 uv run python -m compileall -q src tests 与 git diff --check，均通过。
