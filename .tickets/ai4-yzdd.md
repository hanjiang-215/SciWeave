---
id: ai4-yzdd
status: open
deps: []
links: []
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

- [ ] 不设置环境变量，只传入路径就能打开并建表；连续建表两次仍成功，索引还在
- [ ] 记一条读调用后，查询得到一行，阶段是 `attempted`，结果是 `unknown`，摘要和 `refs` 往返不变
- [ ] 读调用写入失败时返回空、不抛异常
- [ ] 打开或建表失败时抛审计库不可用
- [ ] 表的列集合与约定一致，没有入参正文列；内存库建表不因日志模式失败

## Blocked by

None (can start immediately).

