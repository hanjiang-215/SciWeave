---
id: ai4-dy2x
status: open
deps: [ai4-9f7i, ai4-ebqx, ai4-e257, ai4-saug]
links: []
created: 2026-10-16T00:37:54Z
type: grilling
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:grilling, product, ai4science]
---
# 研究变更 Proposal / PR 治理

## Question
哪些研究变化需要通过类似 PR 的 Proposal？需要在宏观层面决定：路线图变更、资源变更、Agent/Skill 能力变更、结论变更分别如何提出、审查、批准、拒绝和保留历史。暂不讨论代码级实现。

## Acceptance Criteria

明确 Proposal / PR 的适用范围、主要变更类型和审查闭环；保证 Agent 可以提出变化但不能无控制地改变公共研究事实。

## Notes

**2026-10-17T01:53:26Z**

边界修正：Proposal 按领域分别维护。Mapping Proposal 只能修改 Research Mapping；Wiki Proposal 只能修改 LLM-Wiki。一个 Proposal 不得同时包含 Mapping ChangeSet 和 Wiki ChangeSet；Central Agent 可通过两个独立管理 MCP 分别处理它们，但不执行跨域写入。
