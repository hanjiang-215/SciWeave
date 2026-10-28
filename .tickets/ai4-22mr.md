---
id: ai4-22mr
status: open
deps: []
links: [ai4-349h]
created: 2026-10-28T05:58:53Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-w73z
tags: [centre-control, governance, prereview, mcp]
---
# 领域 MCP 缺预审报告读工具：Project Owner 看不到 checks 与 conflict_matrix

append_prereview_log 把报告写进了 mapping_prereview_report / wiki_prereview_report，但两个领域的管理 MCP 都没有读它的工具。SQLiteStore.current_prereview_report 与 status_for_candidate 存在，只在内部用。

后果有两处：

1. Project Owner 决定要不要批准一个候选时，看不到这份候选的判据结论。他能看到候选本身，看不到「四项检查各是什么结果、与同批哪些候选冲突」。预审报告写了，但读者只有运维（查库）。
2. PO 侧的 owner-impact-preview 技能要靠 report_stale / missing_report 做交叉引用，目前只能由人查库判断，无法在工具面表达。

需要的形状：一个只读工具，capability 用 read（PO 已有的档，不需要新能力），入参是 (域标识, candidate_id, candidate_head?) 或者直接复用 list_reviewable_candidates 的返回形状加一列报告状态；出参带 verdict、checks、conflict_matrix、rule_set_version、base_formal_revision_id、created_at，以及一个由 (candidate_head, base_formal_revision_id) 是否仍是当前值推出的状态 current/stale/missing。

不要在这个工具里做裁决。它只把已写入的事实读出来；批准仍然是 formalize_candidate。

## Acceptance Criteria

- [ ] research-map 与 research-wiki 各有一个只读的预审报告工具，capability 为 read
- [ ] 出参含 verdict / checks / conflict_matrix / rule_set_version / base_formal_revision_id / created_at
- [ ] 出参含一个由 head 与 base 是否仍为当前值推出的状态：current / stale / missing
- [ ] 工具不入任何写能力，PO 令牌即可调用，centre 令牌也可调用
- [ ] 卡片同步：central 侧与 PO 侧各加这条工具，且不越界（不出现 formalize 类）
- [ ] 有测试覆盖三种状态，其中 stale 由移动 candidate_head 触发

