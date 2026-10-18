---
id: ai4-xup8
status: open
deps: []
links: [ai4-x3nx, ai4-r3so, ai4-saug, ai4-iciy]
created: 2026-10-18T14:54:19Z
type: epic
priority: 1
tags: [wayfinder:map]
---
# Research Mapping 与 Wiki 领域数据模型和持久化规格地图

## Design

## Destination
形成可交给实现规划的 Research Mapping 与 LLM-Wiki 领域数据模型和持久化规格，明确 TaskNode/Dependency Edge 等对象的具体字段、候选治理的 SQLite 结构化元数据，以及它们与 TerminusDB 正式/候选版本的关联。

## Notes
领域：版本化 Research Mapping 与 LLM-Wiki。
遵循既有领域决策：两个领域治理语义可共用，但 MCP、存储、校验和审计边界独立。
本地图聚焦领域对象、字段含义、约束和存储归属；具体 API、算法实现和产品代码不在目标内。已完成的产品决策与 TerminusDB 行为验证作为输入，不重新讨论。

## Decisions so far

## Not yet specified

## Out of scope
- 具体 MCP/API 参数、冲突检测算法、消息队列产品选型、代码实现和部署架构。
