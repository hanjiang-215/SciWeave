---
id: ai4-fmc9
status: closed
deps: []
links: []
created: 2026-10-29T02:55:02Z
type: chore
priority: 3
assignee: hanjiang
---
# email 仅设 FROM_ADDRESS 时被静默忽略

审查报告第三节：只设 from_address 其余为空时走全未配置分支，from_address 被忽略、/health 报 not_configured，但无任何提示。改为告警并拒绝明显非法的地址。

## Acceptance Criteria

1) 合法地址告警保留；2) 非法地址 ValueError；3) 测试覆盖

