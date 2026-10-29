---
id: ai4-iyik
status: closed
deps: []
links: []
created: 2026-10-29T02:55:01Z
type: chore
priority: 3
assignee: hanjiang
---
# worker.centre_root 依赖 parents[3]，移动源码即断

审查报告第三节：centre_root 用固定层级定位，源码移动后失效。改为向上查找含 definitions 的目录。

## Acceptance Criteria

1) 按标记定位；2) 找不到时退回旧层级；3) assembly/deployment 测试通过

