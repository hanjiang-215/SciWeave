---
id: ai4-tcub
status: closed
deps: []
links: []
created: 2026-10-29T02:23:30Z
type: bug
priority: 2
assignee: hanjiang
---
# wiki owner 决策缺 CAS：并发两次决策后者静默覆盖前者

审查报告 S10 复核成立：review.decide 在 BEGIN IMMEDIATE 内只校验状态集合，无 expected_owner_event_id；审计追加与正式化固定 owner_event_id 限制了影响，但缓冲状态可被静默覆盖。

## Acceptance Criteria

1) decide 接受可选 expected_owner_event_id，不匹配时返回 rejected/stale_owner_decision；2) 不传时行为不变；3) MCP 工具透传该参数；4) 测试覆盖匹配与不匹配

