---
id: ai4-8k4y
status: closed
deps: []
links: [ai4-25wy, ai4-8ybr]
created: 2026-10-21T12:15:12Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, scheduling]
---
# 调度与可修复失败的处置

中央 Agent 按正式路线和前置条件分派任务，并对普通失败做重试、转交或请求人工接管；改变研究假设、前置条件或路线的失败必须走 Mapping Proposal。

## Design

依据「首版任务执行模型」：transient、environment 和可修复的 input 失败可重试，沿用同一 TaskNode 版本并新建 Execution Record；accepted 只表示节点负责人接纳，不代表正式发布。

待定：调度与 Task Agent Gateway 的交接形态（直接调用还是经消息队列）、并发与资源上限。

## Acceptance Criteria

- 只读正式 Mapping 判断前置条件，候选不可见
- 重试不新建 TaskNode 版本
- 路线变化的失败不会被当作普通失败重试
- 每次处置经留痕工具记录


## Notes

**2026-10-21T12:48:15Z**

2026-10-21 关闭：中央 Agent 职责收窄为「部署 Task Agent」与「候选版本预审与合并」，不再承担调度、重试与转交。首次执行改由 Project Owner 经自己的 MCP 触发。收窄依据与推翻条目见 docs/data-flow/centre-agent-scope-reduction.md；相关已关闭票为 ai4-vbnr（assignee SciWeave）与 ai4-m0vt（assignee hanjiang），其负责人可裁决是否接受。
