---
id: ai4-qstm
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 2
assignee: hanjiang
tags: [bug, centre-control, research-map, research-wiki]
---
# 研究域与 Wiki 的若干契约缺陷：混合候选基准、正式化幂等、preview 崩溃、重复定义

create_merged_candidate 用 setdefault 忽略传入的 base_formal_revision_id，也不校验各来源同一基准。Wiki formalize 在操作已成功时返回 reconciliation_required，与 research-map 的重试契约不一致。Wiki preview 在 base 行缺失时对 None 取属性抛 AttributeError，而非返回 stale_base。research-wiki terminus_store.py 的 read_exact_snapshot/_document_commit_url 各定义两次，前一对不可达。

## Acceptance Criteria

混合候选拒绝基准不一致的来源并强制写入传入基准。|Wiki formalize 重放时按 reconciliation 的判据返回 succeeded。|preview 在 base 缺失时返回 stale_base。|删除 terminus_store.py 的重复定义。|各补一条测试。

