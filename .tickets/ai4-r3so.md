---
id: ai4-r3so
status: open
deps: [ai4-ebqx, ai4-u3rs]
links: []
created: 2026-10-16T13:42:18Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, domain-model, ai4science]
---
# Research Mapping 节点与依赖边字段模型

细化统一 Research Mapping 中 TaskNode 与 DependencyEdge 的领域字段、必填条件、字段语义、状态约束和对象间关系。只确定产品/领域模型，不进入数据库列、API 参数或代码结构。字段模型需要为执行模型和 Proposal 治理提供稳定引用，但不在本票据内替代它们做状态决策。

## 需要多人讨论的问题

- TaskNode 的稳定身份、候选版本、Formal MappingRevision 版本和执行实例如何区分；哪些字段不可原地修改，哪些变化必须产生新版本？
- TaskNode Owner、实际执行者、Personal Agent、Task Agent、Central Agent 和 Project Owner 的引用是否属于同一责任字段，还是需要区分负责、执行、预审、接纳和正式发布责任？
- 节点状态与 `Execution Record` 状态如何解耦；一个节点多次执行、重试、转交、人工接管或并行执行时，字段如何保持可追溯和幂等？
- DependencyEdge 如何表达前置条件、阻塞关系、失败后路线变化和候选 Diff；哪些变化只影响执行，哪些变化必须进入 Mapping Proposal？
- Formal Query 和正式调度需要读取哪些节点、边、资源引用和版本字段；如何保证候选或未审核字段不会被普通查询误读为正式事实？

## Acceptance Criteria

- [ ] 形成 TaskNode 与 DependencyEdge 的字段清单和字段语义，标明每个字段的稳定身份、版本、必填/可选、可变性和来源。
- [ ] 明确 TaskNode 的目标、范围、输入、输出、完成条件、负责人、执行主体、人工判断点、资源引用和前置条件的最小表达。
- [ ] 明确 DependencyEdge 的方向、关系类型、前置条件、阻塞语义、条件/分支语义和版本引用规则；禁止把执行日志或资源正文塞入边。
- [ ] 明确节点与边的状态约束、候选/正式版本边界，以及创建、替代、废弃和路线变化的表达；不把 TerminusDB Commit 直接当作产品批准状态。
- [ ] 为 `Execution Record`、MCP Submission、AuditEvent 和 Mapping Proposal 提供稳定的最小关联键与版本引用，但把状态转换和审计字段的最终规则交由对应决策票确定。
- [ ] 覆盖任务规划、执行、资源引用、失败与路线演化的最小表达，包括重复执行、重试/转交/人工接管和结果接纳后的引用位置。
- [ ] 明确普通查询、Formal Query 和正式调度所需的资格字段及过滤边界，确保 TaskNode/DependencyEdge 的候选版本不会进入正式视图。
- [ ] 明确节点和边在跨场景示例替换时保持场景中立，不引入具体学科对象；不进入数据库列、API 参数或代码结构。
