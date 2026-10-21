---
id: ai4-oebi
status: open
deps: [ai4-5z9e]
links: [ai4-5z9e, ai4-8dgd]
created: 2026-10-21T12:14:51Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
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


**2026-10-21T23:45:00Z**

2026-10-21 第五轮讨论的修订。本票挂到「中央 Agent 候选预审职能地图」(ai4-fv1r) 之下，并收窄为只承载混合候选：

- **混合候选确认保留**，不再是「待定」。生成方式、作者身份、操作权与禁止二次混合的约束见「混合候选的生成与作者身份」(ai4-8dgd)。
- **「采用单个」与「建议放弃」两种方案不属于本票**：建议放弃属于预审结论，「采用单个」是 PO 的选择而不是中央 Agent 的合成产物。本票只剩混合候选的生成与送审。
- **冲突矩阵移出本票**：它与「先看哪个候选」的判断一起并入「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e) 的报告格式。
