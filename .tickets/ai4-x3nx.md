---
id: ai4-x3nx
status: closed
deps: []
links: [ai4-ru15, ai4-xup8]
created: 2026-10-18T14:03:32Z
type: epic
priority: 1
assignee: hanjiang
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

- [正式版本前进后候选重放与冲突审核规则](ai4-iciy.md)：候选完整状态保存在 TerminusDB，SQLite 保存治理元数据；中央 Agent 对同一正式基准上的有效候选整体进行语义分析并生成方案，PO 查看完整材料后通过专用 MCP 选择或要求生成新候选；正式化成功后逐项记录来源提交的处置并通知提交者，原提交保留且不因混合而复用。

## Not yet specified


## Out of scope
- TerminusDB API、冲突检测算法实现和存储清理机制的具体技术设计。

## Acceptance Criteria

明确候选相对正式基线的身份与保留规则；明确正式基线前进后的重放、冲突分类和审核边界；明确结构化变更摘要的决策用途；明确 Research Mapping/Wiki 与首版/后续能力范围；形成可用于后续规格设计的闭环规则。

**2026-10-20T07:44:05Z**

负责人转交（2026-10-20）：原负责人 Frank Qi。按项目所有者指示，产品与需求、Research Mapping、LLM-Wiki 模块的工单负责人统一为 hanjiang（即 zhanyunfei）；本票同时归属 Research Mapping 与 LLM-Wiki，因此一并转交。
