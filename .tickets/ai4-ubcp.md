---
id: ai4-ubcp
status: closed
deps: []
links: []
created: 2026-10-29T01:43:38Z
type: bug
priority: 0
assignee: hanjiang
---
# coordinator 重复派发绕过 attempt 计数且 max_attempts 配置失效

技术审查 P0-4/P0-5：service.py:520-525 旧 dispatch 直接再 publish 绕开 _retry_dispatch 的 max_attempts/dead；main.py:113 未把 config.max_attempts/retry_* 传给 CoordinatorService。

## Acceptance Criteria

已存在 dispatch 走 retry 路径并累加 attempt_count；max_attempts 从配置传入并生效；测试覆盖重复派发与上限。
## Notes

2026-10-29 hanjiang：已修复，提交 83bff1。

- 三处 dispatch 发布路径（ready / human notification / terminal summary）统一为 if dispatch is None: return False、if status == published: return True、if status != created: return False；重复触发不再被当成“已发布”从而绕过 max_attempts。
- store.py：dispatched_unknown 的后继状态集合补上 eady，允许重试回到可派发。
- _upsert_pending 对被拒绝的状态迁移记录日志，不再静默丢弃。

验证：coordinator 92 passed / 2 skipped，新增 	est_repeating_a_ready_dispatch_does_not_bypass_max_attempts。