---
id: ai4-9mfd
status: closed
deps: []
links: []
created: 2026-10-29T02:55:02Z
type: bug
priority: 2
assignee: hanjiang
---
# web-ui 时间格式化无防护、RouteView watch 抖动、attentionItems 字典序比较

审查报告第三节三条：new Date/Intl 无防护，非法时间抛 RangeError 中断渲染；RouteView 两个 watch 互相触发；attentionItems 用 ISO 字符串 localeCompare，跨时区排序错误。

## Acceptance Criteria

1) 统一 formatInstant，非法返回占位符；2) 两向 watch 抑制重入；3) 按真实时刻排序；4) vitest + vue-tsc 通过

