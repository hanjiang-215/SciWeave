---
id: ai4-jmiv
status: closed
deps: []
links: []
created: 2026-10-29T03:03:27Z
type: chore
priority: 3
assignee: hanjiang
---
# wiki 域不一致仅启动告警，/health 不体现

技术缺陷报告 B12：wiki 启动时 _warn_if_domain_mismatch 只打日志；健康检查不反映配置域与数据域不一致，故障时仍报 ready，需更显式。

## Acceptance Criteria

1) 域不一致时健康检查返回明确状态/原因；2) 一致时行为不变；3) 测试覆盖

