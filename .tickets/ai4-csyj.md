---
id: ai4-csyj
status: open
deps: []
links: []
created: 2026-10-19T01:14:45Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [wayfinder:grilling]
---
# TaskNode 交接消息发布与下游触发流程

## Question
明确任务完成且审核通过后，沿 TaskNode 与 Dependency Edge 向下游负责人或 Task Agent 发布交接消息的完整流程。需要决定交接消息的触发条件、消息载荷、接收者分发、依赖激活、重复投递、失败重试、下游确认与阻塞解除语义。该票不讨论审核协作会话本身，也不选择具体消息队列产品。

## Acceptance Criteria

形成可交给后续规划的 Task Handoff Message 流程规格：明确发布前置条件、消息结构、沿依赖边的路由与多接收者处理、投递状态、重复与失败恢复、接收确认和下游任务解除阻塞规则。
