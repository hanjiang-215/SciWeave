---
id: ai4-1qyc
status: open
deps: [ai4-z0lb]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 正式化与失败恢复纵向实现

实现 Mapping Project Owner 对固定 Merge Request Buffer 的批准/驳回与正式化路径，并覆盖 TerminusDB Commit 已确认但 SQLite 激活失败或结果未知时的幂等重试、读回对账和恢复。

## Design

严格实现 ai4-azx2 已关闭的跨存储正式化规格：精确 TerminusDB Commit 写入并读回确认后，SQLite 单一激活单元创建 Formal MappingRevision、条件切换当前指针、写入成功结果并收敛治理状态；SQLite 激活提交是唯一生效点。不执行跨存储回滚，未激活 Commit 保留为不可查询历史。

## Acceptance Criteria

- [ ] 未经授权的批准、过期/冲突请求或未锁定候选不能正式化。
- [ ] 两侧确认成功后才出现新的正式版本；SQLite 激活提交前普通查询仍只能看到此前正式版本。
- [ ] TerminusDB 已确认而 SQLite 未确认时，重试复用同一操作和精确 Commit，不生成重复 Formal MappingRevision。
- [ ] 激活结果未知时进入显式需对账状态；通过读回恢复，不盲目重复创建版本。
- [ ] 通知失败不撤销正式版本；对账、修复和人工处置追加审计记录。
- [ ] 自动化/集成验证覆盖成功、驳回、候选过期、图写入失败、SQLite 激活失败及未知结果恢复。
