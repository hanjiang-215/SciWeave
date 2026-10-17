---
id: ai4-xrxw
status: open
deps: [ai4-ay0e, ai4-r3so]
links: [ai4-u3rs, ai4-dy2x]
created: 2026-10-17T15:21:25Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, proposal, audit, product, ai4science]
---
# 首版 Mapping Proposal 生命周期与审计证据模型

明确 Research Mapping 首版 Proposal 的生命周期、Formal Mapping 查询与正式调度门槛、候选 Diff/影响预览和 AuditEvent 最小关联。只确定产品与领域治理规则，不复制 TerminusDB 的存储实现，也不扩展 LLM-Wiki。

## Design

建议围绕一个 Proposal 从 MCP Submission 到 Buffer、候选版本、TaskNode Owner 接纳、中央 Agent 预审、Project Owner Formal Publication Review、批准/驳回/废弃和正式 Revision 的闭环定义状态与不可逆边界；Formal Query 和正式调度只面向当前 Formal MappingRevision；Diff/影响预览必须能解释将改变的节点、边、依赖可达性、任务调度资格和证据引用；AuditEvent 至少关联提交、执行记录、审查、决策、候选/正式版本和操作者。

## Acceptance Criteria

形成 Proposal 状态清单、转换规则和并发/锁定语义；明确 MCP Submission、candidate head、Diff、影响预览、Merge Request Buffer 与 Formal MappingRevision 的最小关系；明确普通查询、候选预览、Formal Query 和正式调度的边界；明确 TaskNode Owner 接纳审核与 Project Owner 正式发布审核的责任边界；明确 AuditEvent 的最小字段和关联对象；明确被拒绝/未选中/废弃候选的保留与只读审计规则；不引入具体技术实现。
