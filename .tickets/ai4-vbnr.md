---
id: ai4-vbnr
status: closed
deps: [ai4-9f7i, ai4-ebqx, ai4-e257, ai4-dy2x]
links: [ai4-m0vt]
created: 2026-10-16T00:37:54Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, product, ai4science]
---
# 中央协调 Agent 与审计体系

## Question
中央 Agent、项目负责人和其他审核者如何分工？需要在宏观层面决定：中央 Agent 负责哪些协调和预审工作，负责人如何进行最终审计，哪些操作需要人工批准，以及平台如何提供完整执行留痕。暂不讨论模型选择和权限系统实现。

## Acceptance Criteria

明确中央协调、人工审计、风险分级和可追溯记录的一级功能；形成平台治理边界。

## Notes

**2026-10-17T01:53:26Z**

边界修正：Central Agent 保持为一个 Agent，但配置独立的 Mapping 管理 MCP 和 Wiki 管理 MCP。两个管理 MCP 背后的 Buffer、TerminusDB、Revision、审核和审计链完全隔离；Central Agent 负责路由和各领域预审，不通过单个提交跨域修改。

**2026-10-17T14:42:44Z**

## Answer

SciWeave 首版采用“中央 Agent 负责协调，Project Owner 负责所有正式事实发布”的人工控制边界。Central Agent 保持为一个 Agent，通过独立的 Mapping 管理 MCP 和 Wiki 管理 MCP 处理两个隔离领域；它不获得替代人工批准的权限。

### Central Agent 可以自动完成的工作

- 读取当前 Formal Mapping、任务状态、已授权 Agent 和可用能力；
- 将任务分派给人员、Personal Agent、Task Agent 或协作集合；
- 检查任务前置条件、提交格式、对象引用、重复提交、权限范围和影响范围；
- 生成候选 Proposal 的结构 Diff、依赖检查和影响预览；
- 推进已批准的候选存储操作，并把结果关联到 Formal MappingRevision；
- 处理普通执行失败的重试、转交和人工接管；
- 记录提交、调度、执行、失败、预审、审核、批准、驳回和正式化事件。

### 必须由 Project Owner 人工批准的工作

- 任何会改变 Formal Mapping 拓扑、任务目标、完成条件、依赖语义或路线激活条件的变更；
- 任何把 Agent 或研究人员输出提升为项目正式共享科研结果的操作；
- 任何路线回滚、恢复、废弃后重新启用或基准版本变化后的正式化；
- 任何 Central Agent 标记为冲突、过期、影响范围不明或违反治理规则的候选。

批准不是对模型生成内容的自动背书，而是 Project Owner 对候选 Diff、影响范围、来源和审核意见作出的明确选择。未经批准的候选不得进入正式查询或正式调度。

### 审计与失败边界

每次受控操作至少记录 actor、actor_type、operation、target_id、base_revision、candidate_revision（如有）、result、timestamp、reason 和关联 Proposal/Task/Resource 标识。审计记录追加写入，不通过覆盖或删除历史记录实现回滚。

普通执行失败可由 Central Agent 重试、转交或请求人工接管；如果失败改变了研究假设、任务前置条件或路线，则必须提交 Mapping Proposal。审计查询能够按任务、Proposal、Formal MappingRevision 或时间顺序重建“谁在什么基准上做了什么、结果如何、谁批准了正式变化”。

首版不引入复杂的风险评分或自动发布等级：是否进入正式事实只有一个明确规则，即必须经过 Project Owner 的人工批准。并行候选、自动冲突解决和跨域审计聚合属于后续能力。
