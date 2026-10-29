---
id: ai4-4g9s
status: open
deps: []
links: []
created: 2026-10-29T05:08:31Z
type: chore
priority: 3
assignee: hanjiang
---
# 候选分支持续累积需清理/回收策略

E2E 观察3：每次候选提交在 TerminusDB 留一个 candidate-* 分支，仓库分支持续增长。需提供候选分支清理/回收策略（过期/已正式化后的分支回收），并可从运维脚本调用。

## Acceptance Criteria

1) 可识别可回收的候选分支（已正式化/过期）；2) 提供回收接口或脚本，默认安全不误删活跃分支；3) 测试覆盖判定逻辑

