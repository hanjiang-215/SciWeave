---
id: ai4-x3nx
status: open
deps: []
links: [ai4-ru15]
created: 2026-10-18T14:03:32Z
type: epic
priority: 1
assignee: Frank Qi
tags: [wayfinder:map]
---
# Research Mapping 与 Wiki 候选变更并发治理地图

## Design

## Destination
形成 Research Mapping 与 Wiki 候选变更并发治理的产品决策，明确正式基线前进时如何保留、分析、重放、审核和正式化其他候选，并给出可交接规格设计的规则。

## Notes
领域：版本化研究图与 Wiki 治理。
依赖现有 SciWeave 产品边界、Proposal 生命周期及 TerminusDB 分支验证；只讨论产品与领域规则，不规定数据库 API 或实现算法。

## Decisions so far

## Not yet specified
- 一项候选正式化后，其他基于旧正式版本的候选如何处理。
- 中央审核怎样区分可无损重放、冲突和语义不确定，结构化摘要需呈现哪些信息。
- 重放后的候选是否需要重新审核、哪些变更应作为不可拆分的整体。
- 这些规则如何覆盖 Research Mapping 与 Wiki，以及首版与后续能力的边界。

## Out of scope
- TerminusDB API、冲突检测算法实现和存储清理机制的具体技术设计。

## Acceptance Criteria

明确候选相对正式基线的身份与保留规则；明确正式基线前进后的重放、冲突分类和审核边界；明确结构化变更摘要的决策用途；明确 Research Mapping/Wiki 与首版/后续能力范围；形成可用于后续规格设计的闭环规则。