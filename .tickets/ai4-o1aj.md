---
id: ai4-o1aj
status: closed
deps: []
links: []
created: 2026-10-29T01:43:45Z
type: bug
priority: 1
assignee: hanjiang
---
# map 候选在 TerminusDB 已写后才拒 base，产生孤儿 commit

技术审查 P1-5：research-mapping/candidate_submission.py:142-143 terminus 已写候选后因 SQLite 无 base 返回 rejected，不回滚/不对账，形成悬挂分支。

## Acceptance Criteria

该路径走 result_unknown 对账或先校验后写；测试覆盖无孤儿分支。
## Notes

2026-10-29 hanjiang：已修复，提交 963221b。

- candidate_submission.submit 在 TerminusDB 已提交候选后才发现 base 修订缺失时，改为 esult_unknown / ase_revision_missing_after_store_write，不再返回 ejected 假装什么都没发生（否则孤儿分支无人收敛）。

验证：esearch-map 137 passed，新增 OrphanCandidateCommitTests。