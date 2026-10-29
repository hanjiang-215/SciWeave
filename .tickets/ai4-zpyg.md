---
id: ai4-zpyg
status: closed
deps: []
links: []
created: 2026-10-29T01:43:45Z
type: bug
priority: 1
assignee: hanjiang
---
# coordinator dispatched_unknown 节点在 recompute 变僵尸

技术审查 P1-6：store.py:40-41 dispatched_unknown 合法后继不含 ready，recompute 命中同节点时 _upsert_pending(ready) 抛 InvalidPendingTransition 被吞成 False，节点既不重发也不报告。

## Acceptance Criteria

明确 dispatched_unknown 可由 recompute 提升为 ready 或留可观测日志；测试覆盖恢复路径。
## Notes

2026-10-29 hanjiang：已修复，提交 83bff1（与 ai4-ubcp 同一改动集）。

- CoordinatorService 接受 max_attempts，main.py 从配置传入并打印生效值；此前该配置项从未被使用，配置了也不生效。
- config.py 为 etry_* 三项加注释标记为预留未使用，max_attempts 标记为实际生效，避免误以为限流已开启。

验证：coordinator 92 passed，新增 	est_main_passes_max_attempts_from_config 断言装配链路。