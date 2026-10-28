---
type: concept
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [mapping, wiki, governance, terminusdb]
---

# Research Mapping 与 LLM-Wiki

两个领域共享治理语义，但保持领域对象、存储、MCP 和审计边界独立。

## Research Mapping

Research Mapping 用版本化 `TaskNode` 和 `DependencyEdge` 表达研究路线。节点包含任务负责人、执行主体引用和生命周期；边精确引用源节点版本与目标节点版本，并声明依赖类型、所需输出和激活条件。

数据分层：

- TerminusDB：保存候选与正式路线的不可变图快照。
- SQLite：保存 Proposal、审批、正式版本指针、治理索引和审计记录。
- 管理 MCP：提供正式只读、候选提交/审阅、预审报告、混合候选、正式化和健康检查。

正式调度只读取正式 MappingRevision 中的正式节点和边。目标节点或依赖边仍为 candidate 时，Coordinator 只能保存等待事实或通知负责人，不能生成可执行交接。

## LLM-Wiki

LLM-Wiki 管理 Wiki 文档、资源版本、引用资格、候选 Proposal 和正式 WikiRevision。资源引用必须绑定精确的 `ResourceVersion` 和使用范围；资格审核与 Project Owner 的正式发布审核是两个不同门槛。

它使用独立的领域 MCP、TerminusDB 图快照、SQLite 治理索引和审计边界，与 Mapping 共用候选、预审、正式化的治理思想，但不共享领域正文。

## 领域治理顺序

1. 人或端侧 Agent 先在 Draft Buffer 形成草稿。
2. 人审核草稿并将已接受草稿通过领域 MCP 推进到候选分支。
3. 领域服务执行候选机械校验。
4. Centre Agent 追加预审报告，必要时创建混合候选。
5. Project Owner 预览影响、批准或退回候选并正式化。
6. 正式版本激活后发布治理事件，供 Coordinator 继续处理依赖。

## 能力分档

| 能力 | 典型调用者 | 作用 |
|---|---|---|
| `read` | 领域参与者 | 读取正式和允许访问的候选 |
| `candidate_submit` | 研究员/端侧 Agent | 提交候选变更 |
| `candidate_review` | Owner | 审阅候选 |
| `formalize` | Project Owner | 正式化候选 |
| `centre` / `prereview_log` / `merged_candidate` | Centre Agent | 全量候选预审、追加报告、创建混合候选 |

令牌由服务端映射调用者身份，客户端不能靠自报角色越权。

## 相关页面

- [[concepts/core-flow]]
- [[concepts/work-agents-and-governance]]
- [[sources/repository-facts]]
