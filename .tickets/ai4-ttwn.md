---
id: ai4-ttwn
status: closed
deps: []
links: []
created: 2026-10-29T01:43:45Z
type: bug
priority: 1
assignee: hanjiang
---
# wiki 正式化幂等误报与激活吞错

技术审查 P1-2/P1-3：formalization.py:28-29 prior.state=='succeeded' 无条件返回 reconciliation_required；:112-113 激活事务吞全部异常且不探测已提交证据。

## Acceptance Criteria

已成功激活可幂等返回 succeeded（校验 pointer/revision/result/exact）；区分已提交与回滚；测试覆盖幂等重试。
## Notes

2026-10-29 hanjiang：已修复，提交 1e95469。

- 幂等：已 succeeded 的操作重放时先跑 econcile()，证据一致即返回 succeeded/lready_activated，不再无条件要求人工对账。
- 取证：激活事务的 except Exception 增加 _activation_landed() 探测（指针 + 修订 + 结果三处一致），commit() 抛错但实际已落库的情况按成功返回。
- econcile() 在域解析为空时返回 merge_request_domain_unresolved，不再拿 NULL 域查库。

验证：esearch-wiki 152 passed；	est_formalization.py 中原本断言“重放必须 reconciliation_required”的旧期望同步改为断言幂等成功（该断言固化了缺陷行为）。