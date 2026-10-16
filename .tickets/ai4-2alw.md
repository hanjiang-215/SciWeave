---
id: ai4-2alw
status: open
deps: [ai4-9hcj]
links: []
created: 2026-10-16T04:16:17Z
type: task
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:task, terminusdb, mapping, ai4science]
---
# TerminusDB 候选分支与草稿工作区行为验证

## Question
在 TerminusDB 12.0.8 中确认 HTTP API 和原生命令创建候选分支的正确参数与行为：候选分支是否能从 main 创建、是否可以在分支中提交节点变更、如何查看分支差异、如何合并到 main，以及是否存在不产生正式 Commit 的草稿工作区。验证结果用于决定 Proposal 待审核变更应放在 TerminusDB 分支、独立数据库还是平台侧状态中。

## Acceptance Criteria

记录可复现的分支创建、提交、Diff、合并/恢复命令或明确证明不支持；给出待审核 Proposal 的存储建议；不得使用未确认的 Git 式分支语义。
