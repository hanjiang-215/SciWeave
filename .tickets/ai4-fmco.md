---
id: ai4-fmco
status: closed
deps: []
links: []
created: 2026-10-24T03:41:51Z
type: chore
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [audit-trail, mcp, threading, bugfix]
---
# 共享留痕包支持多线程 MCP 服务访问

centre-control/shared/audit-trail 的 open_connection 使用 sqlite3.connect(path) 默认 check_same_thread=True。领域管理 MCP 是 ThreadingHTTPServer 多线程服务，真实请求线程访问审计连接触发 ProgrammingError，写工具 begin_call 抛 AuditUnavailableError，以 fail-closed 返回 audit_unavailable，导致 submit_candidate/preview_candidate/formalize_candidate 等全部写工具在真实 HTTP 部署下不可用。单线程 unittest 测试无法暴露此问题。修复：open_connection 改 check_same_thread=False，所有入口（init_audit_table/record_attempted/begin_call/finish_call/query_audit_calls/find_unfinished_calls）用 _CONNECTION_LOCK 可重入锁串行化。由 run_iris_mapping_pipeline.py 真实链路暴露并验证。关联 ai4-w73z（管理 MCP）、ai4-tg3v（留痕包规格）。

## Acceptance Criteria

- [x] open_connection 允许跨线程访问且写/读入口串行化
- [x] audit-trail pytest 全量通过
- [x] research-map / research-wiki 全量 unittest 无回归
- [x] Iris 真实 MCP 链路写工具不再返回 audit_unavailable

## Notes

**2026-10-24 修复与验证（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

根因：`open_connection` 使用 `sqlite3.connect(path)`，默认 `check_same_thread=True`。领域管理 MCP 是 `ThreadingHTTPServer` 多线程服务，每个请求在独立线程调用 `MappingManagementService.call_tool`，写工具经 `begin_call` 访问审计连接时触发 `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`，被包成 `AuditUnavailableError` 以 fail-closed 返回 `audit_unavailable`。单线程 unittest 里连接只在主线程使用，故既有测试全绿而真实部署必失败。

修复（提交中）：`open_connection` 改为 `sqlite3.connect(path, check_same_thread=False)`；`init_audit_table`、`record_attempted`、`begin_call`、`finish_call`、`query_audit_calls`、`find_unfinished_calls` 全部经模块级 `_CONNECTION_LOCK`（`threading.RLock`，可重入）串行化，避免同一连接并发交错。

验证：

- `centre-control/shared/audit-trail`：`uv run --locked --with pytest python -m pytest tests -q` → 14 passed。
- `research-map`：90 项 unittest 通过（5 跳过，真实 TerminusDB 集成）。
- `research-wiki`：96 项 unittest 通过（4 跳过）。
- `humans/competition/demo-evidence/run_iris_mapping_pipeline.py` 真实链路：修复前 `submit_candidate` 返回 `{code: audit_unavailable}`，修复后完整跑通 `submit_candidate → preview_candidate → record_review → formalize_candidate → get_formal_mapping`，写工具全部可用，退出码 0。

边界：本票只改共享包，未改领域服务行为；接口层留痕语义（读 attempted fail-open、写 invoked/completed fail-closed）保持不变。`ai4-tg3v`（留痕包规格）由 Frank Qi 负责，如需规格层面同步多线程边界由该票裁决。

