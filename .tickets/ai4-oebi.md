---
id: ai4-oebi
status: open
deps: [ai4-5z9e]
links: []
created: 2026-10-21T12:14:51Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, proposal]
---
# 候选方案合成与送审

中央 Agent 针对同一正式基准上的有效候选，生成一个或多个完整方案（采用单个、混合、建议放弃），并把完整来源、Diff、影响范围和判断依据交给 Project Owner 选择。

## Design

依据「正式版本前进后候选重放与冲突审核规则」：可兼容组合由中央 Agent 提出，任何修改都生成新的不可变候选版本，Project Owner 批准的是确切版本；中央 Agent 不替 Project Owner 做最终选择。

待定：混合方案的生成方式（规则还是模型）、方案数量上限、送审的调用形态。

## Acceptance Criteria

- 方案引用完整来源与基准版本
- 生成的混合结果是新的不可变候选，不改写他人候选
- 语义依据不足的组合不得作为已验证兼容方案呈现
- 中央 Agent 无法替 Project Owner 选择

