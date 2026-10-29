---
id: ai4-2hv6
status: closed
deps: []
links: []
created: 2026-10-29T02:23:30Z
type: bug
priority: 2
assignee: hanjiang
---
# coordinator 空 target_agent_id 时静默 return 会被记成已派发 记成功但没发的防御性缺口；当前只在 executor_agent_id 非空时调用故不可达。

审查报告 S8 复核成立：adapter_publisher 在 allow_unknown_agent_topic 为真（默认）时直接 return，调用方随后把 dispatch 置为 published，形成

## Acceptance Criteria

1) 默认不允许静默丢弃，改为抛错或至少 warning；2) 调用方把它当失败重试；3) 测试覆盖

