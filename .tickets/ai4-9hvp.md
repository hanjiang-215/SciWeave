---
id: ai4-9hvp
status: closed
deps: []
links: []
created: 2026-10-29T05:04:43Z
type: bug
priority: 2
assignee: hanjiang
---
# research-map 候选回读对 Set 字段顺序敏感

E2E 复验(技术缺陷报告 缺陷3)：@type:Set 字段(acceptance_criteria/expected_outputs/required_evidence/executor_refs)TerminusDB 按排序回读，_contains_documents 整字典比较，非字典序提交失配 → 误判 store_result_unknown。修复：比较前对两侧字符串列表字段排序归一化 _normalize_set_fields。

## Acceptance Criteria

1) 归一化仅对字符串列表；2) 顺序不同判等；3) 真实差异仍拒绝；4) 回归测试覆盖

