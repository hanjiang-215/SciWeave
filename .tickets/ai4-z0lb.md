---
id: ai4-z0lb
status: open
deps: [ai4-6s53]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 候选差异与审阅纵向实现

实现 Research Mapping 候选审阅路径：针对固定的正式基线和不可变候选生成结构化差异与影响预览，支持将一份固定候选提交为 Merge Request Buffer，并记录预审/审阅结果，供正式负责人作出最终批准或驳回决定。

## Design

差异与影响范围围绕 TaskNode、DependencyEdge、输入输出及路线激活条件。审阅对象必须绑定明确的 base Formal MappingRevision 和 candidate head；基准变化或候选 head 变化时重新验证并使旧预览失效。最终正式化成功条件仍由独立的正式化任务实现。

## Acceptance Criteria

- [ ] 对指定基准和候选生成可重复读取的结构差异及受影响对象/路线预览。
- [ ] Merge Request Buffer 固定引用 Proposal、候选 head、基准正式版本、预览结果和提交/审阅记录，不复制或改写候选正文。
- [ ] 基准已前进、候选 head 不匹配或候选不可读时明确标记冲突/不可用，不能提交为可批准的有效请求。
- [ ] 记录通过、退回或拒绝等审阅决策及操作者、时间、理由；不授予 Agent 绕过人工正式审核的能力。
- [ ] 自动化测试覆盖无变更、有效差异、基准前进和候选失效场景。
