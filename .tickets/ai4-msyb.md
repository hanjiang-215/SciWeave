---
id: ai4-msyb
status: closed
deps: []
links: []
created: 2026-10-29T05:04:43Z
type: bug
priority: 1
assignee: hanjiang
---
# wiki 候选回读比较未忽略服务端补写的 @id

E2E 复验(技术缺陷报告 缺陷2)：TerminusDB 写入后给文档补 @id，_candidate_documents_match 与 candidate_submission._contains 做整字典相等比较，提交文档无 @id，差集 {@id:[服务端值,null]} 恒不等 → 写入成功仍判 store_result_unknown。修复：比较前剥离 @id。

## Acceptance Criteria

1) 两处比较前剥离 @id；2) 有真实内容差异仍拒绝；3) 回归测试覆盖

