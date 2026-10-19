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

## Notes

**2026-10-19T05:47:44Z**

Wayfinder 前沿结论（2026-10-19）：与端侧 Agent 的协作通道保持分离。Owner 的补充、返修、重试、暂停、取消和 Human Input 通过 A2A Gateway；上游审核通过后的单次 TaskNode 交接通过消息队列和上游收集器。A2A 可向 Owner 返回实时最终文字回复或 INPUT_REQUIRED 状态；上游自动执行完成后，结果写入 Buffer/Execution Record，并只向该 TaskNode Owner 发送一次邮件提醒，邮件不承载任务事实或审核决定。每个 TaskNode 至少有一名 Owner；上游交接只有在必要消息收齐且 Dependency Edge 激活后才触发下游执行。
