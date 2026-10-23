---
id: ai4-3xsp
status: open
deps: []
links: []
created: 2026-10-22T13:24:04Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, ready-for-agent, work-agent, centre-agent]
---
# 把现有项目组迁到 Centre Agent 的家

## Parent

最小 Work Agent 实现规格（ai4-z3z4）。放置依据 ADR-0002。

## What to build

把现有可运行的 Work Agent 项目组换到 Centre Agent 的目录，作为中央那一份的起点。测试保持全绿。不改状态机、不删旧工具、不实现订阅器。迁完不再留第三份源码。

这是后续行为改造的前置，不是新功能。

## Acceptance Criteria

- [ ] 现有项目组位于 Centre Agent 的家，旧路径不再作为第三份源码存在
- [ ] 迁后 Gateway 的既有测试仍然通过
- [ ] 不改变执行状态机、工具面和 Worker 行为

