---
id: ai4-gqj3
status: closed
deps: [ai4-m96w]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# ExecutionRecord 控制、审核与恢复 MCP 工具

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

Task Owner 可取消或列出待跟进执行、回答 Worker 暂停问题；Task Node Owner 可审核结果。所有控制行为经 MCP 和共享 SQLite 持久化，不创建领域 Buffer、草稿或 outbox。

## Acceptance Criteria

## Acceptance Criteria

- [ ] `cancel_execution` 对存在执行返回规定的 `accepted` 语义；不存在执行返回 `not_found`。
- [ ] `list_pending` 支持可选 TaskNode 过滤，按 created_at、execution_id 稳定排序且不分页。
- [ ] `review_execution` 支持接纳、返修、驳回和人工接管，保留审核理由和审计事实。
- [ ] waiting 回答创建带 `resume_of` 的新记录；返修创建带 `revision_of` 的新记录；旧记录不可覆盖。
- [ ] 执行结果接纳不自动创建领域 Buffer、领域草稿或 outbox。
- [ ] 工具内审核幂等键、非法状态迁移和稳定业务错误均有 MCP 行为测试。

## Notes

**2026-10-21T02:19:23Z**

2026-10-21：完成 ExecutionRecord 控制、审核与恢复 MCP 工具。cancel_execution 已实现 accepted 语义及 not_found；list_pending 支持 TaskNode 过滤和稳定排序；review_execution 支持 accept、request_revision、reject 与 request_human_takeover，保存理由、审核幂等事实和审计。返修将旧记录置 needs_revision 并创建带 revision_of 的新 queued 记录；waiting 回答通过 submit_owner_command 的 execution_id 创建带 resume_of 的新记录，复用稳定 session_id。接纳不写入领域 Buffer、草稿或 outbox。验证：cd sci-weave/task-agent && uv run --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v（17 passed）；python3 -m compileall -q gateway/mcp/src；git diff --check。
