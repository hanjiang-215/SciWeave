---
id: ai4-hhs4
status: closed
deps: []
links: []
created: 2026-10-29T01:43:45Z
type: bug
priority: 1
assignee: hanjiang
---
# wiki 候选快照 _contains 弱对账（None==None 命中）

技术审查 P1-4：candidate_submission.py:279-285 _contains 用 reference_id/wiki_revision_id 相等即通过，两侧 None 时 None==None 命中任意文档，快照对账被弱化。

## Acceptance Criteria

按 @id 精确匹配并用 canonical JSON 比较完整文档；测试覆盖篡改/缺失内容被拒。
## Notes

2026-10-29 hanjiang：已修复，提交 e26a201。

- _contains 改为按 @id 匹配并用 canonical JSON 比对整篇文档；无 @id 时要求整篇精确命中。
- 修掉 None == None 通道：此前两侧都缺 eference_id 就会被判为“包含”，篡改或缺失候选可蒙混过关。

验证：esearch-wiki 152 passed，新增 ContainsReconciliationTests（同 id 改正文被拒、完全一致通过、双侧 None 不再命中）。