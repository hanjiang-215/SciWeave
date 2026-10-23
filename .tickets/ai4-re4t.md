---
id: ai4-re4t
status: open
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

