---
id: ai4-yl2o
status: open
deps: [ai4-t5zl, ai4-mjku]
links: []
created: 2026-10-18T15:06:41Z
type: epic
priority: 1
parent: ai4-xup8  # Research Mapping 与 Wiki 领域数据模型和持久化规格地图
tags: [wayfinder:grilling]
---
# Research Mapping 持久化模型分支

Research Mapping 持久化规格分支；统一其图对象字段与本领域 SQLite 提交治理记录。

## Design

## Question
Research Mapping 的 TerminusDB 图对象模型与本领域 SQLite 候选治理记录应如何共同构成一致、可追溯的持久化规格？本父节点汇总并交付其下的字段决策，不重新讨论既有产品语义。

## Acceptance Criteria
TaskNode/Dependency Edge 对象字段与 Research Mapping 专属 SQLite 提交/候选治理字段已分别决定，并能组合成无歧义的数据模型；跨存储一致性由地图下的独立决策票处理。
