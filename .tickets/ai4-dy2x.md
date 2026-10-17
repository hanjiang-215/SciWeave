---
id: ai4-dy2x
status: closed
deps: [ai4-9f7i, ai4-ebqx, ai4-e257, ai4-saug]
links: []
created: 2026-10-16T00:37:54Z
type: grilling
priority: 1
assignee: SciWeave
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

**2026-10-17T08:28:32Z**

本票据后续应采用统一提案治理内核：Mapping Proposal 与 Wiki Proposal 共享 Buffer → candidate branch → candidate head lock → Merge Request Buffer → Formal Revision 的治理语义，但各自使用独立 MCP、Buffer、校验器、TerminusDB 和审计链；不支持跨域 Proposal 或跨域原子正式化。

**2026-10-17T14:38:33Z**

## Answer

SciWeave 首个可演示版本将 Proposal / PR 治理收敛为 Research Mapping 的路线变更治理，不把 LLM-Wiki、ResourceVersion、Agent/Skill/MCP 能力注册变更纳入首版正式化闭环。

### 首版需要 Proposal 的变化

- 新增、废弃或恢复 TaskNode；
- 新增、废弃或调整 Dependency Edge；
- 改变任务目标、完成条件、预期产物、依赖语义或路线激活条件；
- 因失败结果改变研究路线、增加替代路线或重新打开已废弃路线。

以上变化会影响正式 Research Mapping，必须生成结构化 ChangeSet，由 Central Agent 做格式、引用、依赖和影响范围预审，再由 Project Owner 做最终发布审核。

### 首版不需要 Proposal 的变化

- 任务执行开始、暂停、重试、失败和完成等运行状态；
- 执行日志、运行输出和审计事件的追加记录；
- 已存在任务上的普通协作留言和进度汇报。

这些内容仍需通过受控提交保存，并在进入正式共享资源或作为后续路线依据前经过负责人审核，但不改变正式 Mapping 拓扑。

### 审核闭环

首版采用单个 Proposal 的单候选演示路径：MCP Submission → Buffer → Central Agent 预审 → candidate branch / candidate Commit → Diff 与影响预览 → Project Owner 批准或驳回 → Formal MappingRevision。正式分支只由平台在负责人批准后推进；TerminusDB rebase 只承担存储整合，不代表审批。被驳回的候选、Diff、审核意见和审计事件保留为只读记录，后续修订必须基于最新 Formal MappingRevision 创建新的 Proposal。

平台目标仍保留并行候选、冲突解决和 blended candidate 的扩展能力，但不作为 SciWeave 首个演示版本的必需交付物。第一阶段不支持跨 Research Mapping 与 LLM-Wiki 的 Proposal 或原子正式化。
