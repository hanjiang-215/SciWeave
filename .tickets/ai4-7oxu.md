---
id: ai4-7oxu
status: closed
deps: []
links: []
created: 2026-10-29T01:43:38Z
type: bug
priority: 0
assignee: hanjiang
---
# gateway 终态 UPDATE 缺 status 守卫，取消被完成覆盖

技术审查 P0-2：gateway/mcp/src/gateway/app.py:100-106 run_worker_process 结束的 UPDATE 无 AND status='running' 守卫与 rowcount 检查，执行中途 cancel_execution 置 cancelled 后被覆盖为 completed/failed。

## Acceptance Criteria

终态 UPDATE 带 status='running' 守卫；rowcount==0 时保留既有状态并释放租约；新增回归测试覆盖取消竞态。
## Notes

2026-10-29 hanjiang：已修复，提交 3caf8b。

- gateway/app.py 取消路径的终态更新改为 WHERE execution_id = ? AND status = 'running'，owcount == 0 时保留既有终态、释放 lease、继续排空队列，并只在被拦下时记录 worker_lease_released 审计。

验证：gateway 14 passed，新增 CancelDoesNotGetOverwrittenTests 覆盖“取消不覆盖已完成”。