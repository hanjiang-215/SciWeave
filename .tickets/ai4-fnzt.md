---
id: ai4-fnzt
status: closed
deps: []
links: []
created: 2026-10-29T05:08:31Z
type: bug
priority: 3
assignee: hanjiang
---
# 看板 task 投影缺 title 且 logical_id 显示为版本号

E2E 观察2：/api/dashboard/snapshot 的 task 投影 title 为空、logical_id 呈现为 v1 一类版本号，影响展示层可读性。需在投影中补全标题字段、logical_id 使用真正的逻辑 id。

## Acceptance Criteria

1) task 投影含非空 title（有数据时）；2) logical_id 为逻辑 id 而非版本号；3) 无数据时占位合理；4) 测试覆盖

