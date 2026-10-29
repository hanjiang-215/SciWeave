---
id: ai4-t7jc
status: closed
deps: []
links: []
created: 2026-10-29T01:43:38Z
type: bug
priority: 0
assignee: hanjiang
---
# ingest schema_version 非数字崩掉消费 loop

技术审查 P0-3：gateway/ingest/src/gateway_ingest/service.py:83 int(schema_version) 对非数字抛 ValueError，cli.py:178 仅 catch GovernanceEnvelopeError，毒消息终止整个 run_loop。

## Acceptance Criteria

from_dict 内 int() 非法值抛 GovernanceEnvelopeError；cli run_loop 兜底非预期异常；测试覆盖 schema_version='v1' 不崩。
## Notes

2026-10-29 hanjiang：已修复，提交 6107220。

- gateway_ingest/service.py：非法 schema_version 抛 GovernanceEnvelopeError（不再裸 ValueError 逃逸）。
- gateway_ingest/cli.py：消费循环对未预期异常记日志、commit 并继续，单条毒消息不再终止消费进程。

验证：ingest 15 passed；另有 7 个 	est_prereview_sweep 失败为既有环境问题（测试调用 sh 脚本，Windows 下不可用），git stash 前后一致，与本次改动无关。