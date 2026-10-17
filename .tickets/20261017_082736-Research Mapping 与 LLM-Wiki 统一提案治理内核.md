---
id: ai4-3nru
status: closed
deps: []
links: []
created: 2026-10-17T08:27:36Z
type: task
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, wiki, proposal, ai4science]
---
# Research Mapping 与 LLM-Wiki 统一提案治理内核

统一 Research Mapping 与 LLM-Wiki 的 Buffer、Proposal、candidate branch、candidate Commit、candidate head、Merge Request Buffer 和 Formal Revision 治理流程，同时保持两个领域的实现、MCP、存储和审计链独立。

## Design

推荐方案：两个领域共享治理语义和状态转换；各自实现领域 MCP、Buffer、校验器、TerminusDB、Revision 和审计链；允许从同一正式版本派生多个并行 Proposal，但单个候选分支内保持候选版本不可变；Project Owner 最终只选择一个完整方案正式化。

## Answer

Research Mapping 与 LLM-Wiki 采用统一的提案治理内核，但保持领域实现独立。

### 共享治理语义

两个领域都使用同一组逻辑阶段：

```text
Domain Buffer Submission
→ Draft Acceptance Review
→ Domain Proposal
→ candidate branch
→ candidate Commit
→ candidate head lock
→ Merge Request Buffer
→ diff / merge dry-run
→ Project Owner Formal Publication Review
→ Formal Revision
```

共享规则如下：

- candidate branch 只承载候选内容，不代表正式批准；candidate Commit 不可变。
- 一个正式版本可以派生多个并行 Proposal 和 candidate branch；候选之间允许竞争性修改，但不能覆盖其他 Proposal 的原始候选内容。
- 创建 Merge Request Buffer 时固定 candidate head；被引用的 candidate head、祖先 Commit 和 Diff 进入只读审查范围，不能继续追加写入或原地修改。
- Merge Request Buffer 可以包含多个完整候选方案，但 Project Owner 最终只能选择一个完整方案正式化。
- 如果需要组合多个候选，Agent 必须生成新的 `blended` candidate Commit，记录来源、保留内容、舍弃内容和冲突处理说明；不能直接修改原始候选。
- 冲突必须通过领域对应的 diff / merge dry-run 识别；正式分支前进或候选修改同一逻辑对象时，不能直接正式化。
- 正式化生成一个新的领域 Formal Revision；被拒绝、未选中或已完成的候选对象保留为只读审计对象。

### 领域独立实现

共享治理内核不意味着共享实现。Research Mapping 与 LLM-Wiki 分别维护：

- 独立的 Buffer 和管理 MCP；
- 独立的领域校验器和冲突检测器；
- 独立的 TerminusDB、candidate branch 和 formal branch；
- 独立的 Mapping Revision 或 Wiki Revision；
- 独立的 Trace、AuditEvent 和写入权限控制。

Mapping 的冲突检测针对 TaskNode、Dependency Edge、输入输出和路线激活条件；Wiki 的冲突检测针对 WikiDocument、Resource Reference、Entity、Concept 和共享引用关系。

### 跨域边界

第一阶段不支持跨域 Proposal，也不支持一个 MCP Submission 或 Merge Request Buffer 同时修改 Research Mapping 与 LLM-Wiki。需要同时产生两边变化时，Central Agent 通过两个独立管理 MCP 分别创建独立的 Buffer、Proposal 和正式化请求；两个领域之间只通过稳定对象 ID 和版本 ID 建立显式弱引用，不提供跨两个 TerminusDB 的原子正式化。

本决策取代 Research Mapping 中“同一逻辑对象全局只能有一个活动草稿”的限制：并行 Proposal 可以修改同一逻辑对象，但每个 Proposal 的候选版本不可变，最终只能有一个完整方案进入 Formal Revision。
