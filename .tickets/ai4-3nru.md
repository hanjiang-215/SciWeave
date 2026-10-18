---
id: ai4-3nru
status: closed
deps: [ai4-u3rs, ai4-dy2x, ai4-zewm, ai4-36ek]
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

## 首版边界

本票据定义的是未来可复用的治理语义，不扩大 SciWeave 首版交付范围：

- 首版只实现 Research Mapping 的单领域、单候选闭环；不实现 LLM-Wiki 正式化、并行候选、冲突合并或 `blended` candidate。
- LLM-Wiki 的 WikiDocument、WikiRevision、ResourceVersion、candidate branch 和 Proposal 生命周期属于后续架构设计；它们不能成为首版 Research Mapping Demo 的前置依赖。
- 两个领域可以共享术语和治理原则，但不共享对象、数据库、Buffer、MCP Submission、Revision 或审计链。
- 研究人员在首版看到的是“提交路线变更”“查看影响”“批准/驳回草稿”等操作；candidate branch、Commit 和 head lock 只在高级审计或实现层展示。

## Acceptance Criteria

- [x] 明确两个领域共享治理语义，但保持 MCP、Buffer、校验器、存储、Revision 和审计链独立。
- [x] 明确候选版本不可变、candidate head 锁定和正式化必须经过 Project Owner 审核。
- [x] 明确首版只实现 Research Mapping 单领域、单候选路径，不要求实现 LLM-Wiki 完整闭环。
- [x] 明确不支持跨域 Proposal 和跨两个 TerminusDB 的原子正式化。
- [x] 明确并行 Proposal、冲突解决和 `blended` candidate 是后续扩展，不进入首版验收。

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

## Review conclusion (2026-10-18)

本票据的统一治理语义已完成，且明确不把后续 LLM-Wiki 实现当作首版前置条件。首版只采用 Research Mapping、单候选和人工正式审核；并行候选、冲突解决、`blended` candidate 和跨域 Proposal 继续保留为后续扩展。研究人员在首版只看到路线草稿、影响范围、批准或驳回，不需要理解内部版本对象。
